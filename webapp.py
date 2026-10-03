#!/usr/bin/env python3
"""Local web interface for saved CC1101 remote signals."""

from __future__ import annotations

import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for

from profiles import REMOTE_PROFILE, VEHICLE_PROFILES, grouped_vehicle_profiles, profile_for


BASE = Path(__file__).resolve().parent
SIGNALS = BASE / "signals"
VEHICLE_SIGNALS = BASE / "vehicle-signals"
EVENTS = BASE / "events.jsonl"
MONITOR_PID = BASE / ".monitor.pid"
MONITOR_LOG = BASE / "monitor.log"
MONITOR_LOG_ARCHIVE = BASE / "monitor.1.log"
MONITOR_ENABLED = BASE / ".monitor.enabled"
MONITOR_STATUS = BASE / "monitor-status.json"
MONITOR_CONFIG = BASE / "monitor-config.json"
RFCONTROL = BASE / "rfcontrol.py"
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,48}$")
RADIO_LOCK = threading.Lock()
MONITOR_LOCK = threading.Lock()
MONITOR_PAUSED = threading.Event()

app = Flask(__name__)
# Only protects one local session's flash messages; no credential is stored here.
app.secret_key = "pi-cc1101-local-interface"


def load_signals() -> list[dict]:
    SIGNALS.mkdir(exist_ok=True)
    result = []
    for path in sorted(SIGNALS.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            result.append({
                "name": path.stem,
                "label": data.get("name", path.stem),
                "remote_name": data.get("remote_name", data.get("name", path.stem)),
                "button_name": data.get("button_name"),
                "pulses": len(data.get("durations_us", [])),
                "repeats": int(data.get("repeats", 8)),
                "frames": int(data.get("captured_frames", 0)),
                "protocol": data.get("protocol", "RAW"),
                "key": data.get("key"),
                "bits": data.get("bits"),
                "te_us": data.get("te_us"),
                "aliases": data.get("compatible_protocols", []),
            })
        except (OSError, ValueError, TypeError):
            result.append({"name": path.stem, "pulses": 0, "repeats": 0,
                           "frames": 0, "invalid": True})
    return result


def load_vehicle_signals() -> list[dict]:
    VEHICLE_SIGNALS.mkdir(exist_ok=True)
    result = []
    for profile_id, profile in VEHICLE_PROFILES.items():
        folder = VEHICLE_SIGNALS / profile_id
        folder.mkdir(exist_ok=True)
        for path in sorted(folder.glob("*.sub"), reverse=True):
            sidecar = path.with_suffix(".json")
            try:
                details = json.loads(sidecar.read_text()) if sidecar.exists() else {}
            except (OSError, ValueError):
                details = {}
            result.append({
                "name": path.stem, "profile_id": profile_id,
                "profile": profile["label"], "protocol": profile["protocol"],
                "frequency": profile["frequency_label"], "modulation": profile["modulation"],
                "captured_at": details.get("captured_at", ""),
                "validation": details.get("validation", "ungeprüfte Altaufnahme"),
                "validation_score": details.get("validation_score"),
                "validated_frames": details.get("validated_frames"),
                "path": path,
            })
    return result


def monitor_config() -> dict:
    try:
        config = json.loads(MONITOR_CONFIG.read_text())
        profile = profile_for(config.get("mode", "remote"), config.get("profile_id"))
        return {"mode": profile["kind"], "profile_id": profile["id"], "profile": profile}
    except (OSError, ValueError, TypeError):
        return {"mode": "remote", "profile_id": REMOTE_PROFILE["id"],
                "profile": REMOTE_PROFILE}


def load_events(limit: int = 20) -> list[dict]:
    if not EVENTS.exists():
        return []
    events = []
    labels = {}
    for path in SIGNALS.glob("*.json"):
        try:
            labels[path.stem] = json.loads(path.read_text()).get("name", path.stem)
        except (OSError, ValueError):
            pass
    for line in EVENTS.read_text().splitlines()[-limit:][::-1]:
        try:
            event = json.loads(line)
            event["label"] = labels.get(event.get("signal"), event.get("signal"))
            events.append(event)
        except ValueError:
            pass
    return events


def group_signals(signals: list[dict]) -> list[dict]:
    groups = []
    by_name = {}
    for item in signals:
        group_name = item.get("remote_name") or item["label"]
        if group_name not in by_name:
            group = {"name": group_name, "signals": []}
            by_name[group_name] = group
            groups.append(group)
        by_name[group_name]["signals"].append(item)
    return groups


def monitor_pid() -> int | None:
    try:
        pid = int(MONITOR_PID.read_text().strip())
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
        if b"monitor.py" not in command:
            raise ProcessLookupError
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError, ProcessLookupError):
        MONITOR_PID.unlink(missing_ok=True)
        return None


def start_monitor(persist: bool = True, mode: str | None = None,
                  profile_id: str | None = None) -> bool:
    with MONITOR_LOCK:
        if mode is None:
            config = monitor_config()
        else:
            profile = profile_for(mode, profile_id)
            config = {"mode": mode, "profile_id": profile["id"], "profile": profile}
        if persist:
            temporary = MONITOR_CONFIG.with_suffix(".tmp")
            temporary.write_text(json.dumps({"mode": config["mode"],
                                             "profile_id": config["profile_id"]}) + "\n")
            temporary.replace(MONITOR_CONFIG)
            MONITOR_ENABLED.write_text("enabled\n")
        if monitor_pid() is not None:
            return False
        if persist:
            MONITOR_STATUS.unlink(missing_ok=True)
        if MONITOR_LOG.exists() and MONITOR_LOG.stat().st_size >= 2 * 1024 * 1024:
            MONITOR_LOG_ARCHIVE.unlink(missing_ok=True)
            MONITOR_LOG.replace(MONITOR_LOG_ARCHIVE)
        log = MONITOR_LOG.open("a")
        process = subprocess.Popen(
            [sys.executable, str(BASE / "monitor.py"), "--hours", "0",
             "--mode", config["mode"], "--profile", config["profile_id"]],
            cwd=BASE, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log.close()
        MONITOR_PID.write_text(f"{process.pid}\n")
        return True


def stop_monitor(persist: bool = True) -> bool:
    with MONITOR_LOCK:
        if persist:
            MONITOR_ENABLED.unlink(missing_ok=True)
            MONITOR_STATUS.unlink(missing_ok=True)
        pid = monitor_pid()
        if pid is None:
            return False
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            for _ in range(30):
                try:
                    waited, _status = os.waitpid(pid, os.WNOHANG)
                    if waited == pid:
                        break
                    os.kill(pid, 0)
                except ChildProcessError:
                    if not Path(f"/proc/{pid}").exists():
                        break
                except ProcessLookupError:
                    break
                time.sleep(0.1)
        except ProcessLookupError:
            pass
        MONITOR_PID.unlink(missing_ok=True)
        return True


def system_status() -> dict:
    status = {}
    try:
        status = json.loads(MONITOR_STATUS.read_text())
    except (OSError, ValueError):
        pass
    started = status.get("started_at")
    uptime = "–"
    if started:
        try:
            seconds = max(0, int((datetime.now().astimezone()
                                  - datetime.fromisoformat(started)).total_seconds()))
            days, remainder = divmod(seconds, 86400)
            hours, minutes = divmod(remainder // 60, 60)
            uptime = f"{days} T {hours} Std {minutes} Min" if days else f"{hours} Std {minutes} Min"
        except ValueError:
            pass
    disk = shutil.disk_usage(BASE)
    active_config = monitor_config()
    return {
        "uptime": uptime,
        "last_signal": status.get("last_signal") or "Noch keines",
        "last_signal_at": status.get("last_signal_at") or "–",
        "heartbeat": status.get("heartbeat") or "–",
        "disk_free_gb": f"{disk.free / 1024**3:.1f}",
        "event_mb": f"{EVENTS.stat().st_size / 1024**2:.2f}" if EVENTS.exists() else "0.00",
        "profile": active_config["profile"]["label"],
        "mode": active_config["mode"],
    }


def monitor_watchdog() -> None:
    while True:
        time.sleep(30)
        if not MONITOR_ENABLED.exists() or MONITOR_PAUSED.is_set():
            continue
        pid = monitor_pid()
        stale = False
        try:
            heartbeat = json.loads(MONITOR_STATUS.read_text()).get("heartbeat")
            if heartbeat:
                stale = (datetime.now().astimezone()
                         - datetime.fromisoformat(heartbeat)).total_seconds() > 150
        except (OSError, ValueError, TypeError):
            stale = pid is not None and MONITOR_STATUS.exists()
        if pid is None:
            start_monitor(persist=False)
        elif stale:
            stop_monitor(persist=False)
            start_monitor(persist=False)


def run_radio(*arguments: str, timeout: int = 30) -> tuple[bool, str]:
    if not RADIO_LOCK.acquire(blocking=False):
        return False, "Das Funkmodul ist gerade beschäftigt."
    try:
        process = subprocess.run(
            [sys.executable, str(RFCONTROL), *arguments],
            cwd=BASE, text=True, capture_output=True, timeout=timeout,
            check=False,
        )
        message = (process.stdout if process.returncode == 0 else process.stderr).strip()
        return process.returncode == 0, message or "Aktion abgeschlossen."
    except subprocess.TimeoutExpired:
        return False, "Die Funkaktion hat zu lange gedauert."
    finally:
        RADIO_LOCK.release()


@app.get("/")
def index():
    signals = load_signals()
    selected = monitor_config()
    return render_template("index.html", signals=signals, groups=group_signals(signals),
                           events=load_events(), vehicle_signals=load_vehicle_signals(),
                           vehicle_profile_groups=grouped_vehicle_profiles(), selected=selected,
                           monitoring=monitor_pid() is not None, status=system_status())


@app.post("/send/<name>")
def send_signal(name: str):
    if monitor_config()["mode"] == "vehicle":
        message = "Senden ist im Fahrzeugmodus deaktiviert. Wechsle zuerst in den Fernbedienungsmodus."
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify(ok=False, message=message), 403
        flash(message, "error")
        return redirect(url_for("index"))
    if not NAME_RE.fullmatch(name) or not (SIGNALS / f"{name}.json").is_file():
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify(ok=False, message="Unbekanntes Signal."), 404
        flash("Unbekanntes Signal.", "error")
        return redirect(url_for("index"))
    repeats = request.form.get("repeats", "8")
    if not repeats.isdigit() or not 1 <= int(repeats) <= 30:
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify(ok=False, message="Wiederholungen müssen zwischen 1 und 30 liegen."), 400
        flash("Wiederholungen müssen zwischen 1 und 30 liegen.", "error")
        return redirect(url_for("index"))
    arguments = ["send", name, "--repeats", repeats]
    if request.form.get("invert") == "1":
        arguments.append("--invert")
    resume_monitor = monitor_pid() is not None
    MONITOR_PAUSED.set()
    if resume_monitor:
        stop_monitor(persist=False)
    try:
        ok, message = run_radio(*arguments)
    finally:
        if resume_monitor:
            start_monitor(persist=False)
        MONITOR_PAUSED.clear()
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=ok, message=message), 200 if ok else 500
    flash(message, "success" if ok else "error")
    return redirect(url_for("index"))


@app.post("/record")
def record_signal():
    name = request.form.get("name", "").strip()
    if not NAME_RE.fullmatch(name):
        flash("Name: 1–48 Zeichen; erlaubt sind Buchstaben, Zahlen, _ und -.", "error")
        return redirect(url_for("index"))
    if (SIGNALS / f"{name}.json").exists():
        flash("Dieser Name existiert bereits. Bitte einen anderen Namen wählen.", "error")
        return redirect(url_for("index"))
    resume_monitor = monitor_pid() is not None
    MONITOR_PAUSED.set()
    if resume_monitor:
        stop_monitor(persist=False)
    try:
        ok, message = run_radio("record", name, "--seconds", "10", timeout=20)
    finally:
        if resume_monitor:
            start_monitor(persist=False)
        MONITOR_PAUSED.clear()
    flash(message, "success" if ok else "error")
    return redirect(url_for("index"))


@app.post("/delete/<name>")
def delete_signal(name: str):
    if not NAME_RE.fullmatch(name):
        flash("Ungültiger Signalname.", "error")
        return redirect(url_for("index"))
    path = SIGNALS / f"{name}.json"
    if not path.is_file():
        flash("Signal wurde bereits entfernt.", "error")
        return redirect(url_for("index"))
    path.unlink()
    debug = SIGNALS / ".debug" / f"{name}.json"
    if debug.is_file():
        debug.unlink()
    flash(f"{name} wurde gelöscht.", "success")
    return redirect(url_for("index"))


@app.post("/monitor/start")
def monitor_start():
    mode = request.form.get("mode", "remote")
    profile_id = request.form.get("profile_id")
    try:
        profile_for(mode, profile_id)
    except ValueError:
        flash("Unbekanntes Empfangsprofil.", "error")
        return redirect(url_for("index"))
    was_running = monitor_pid() is not None
    if was_running:
        stop_monitor(persist=False)
    started = start_monitor(mode=mode, profile_id=profile_id)
    if started:
        flash("Empfangsprofil gewechselt und gestartet." if was_running
              else "Dauerempfang wurde gestartet.", "success")
    else:
        flash("Dauerempfang läuft bereits.", "success")
    return redirect(url_for("index"))


@app.post("/monitor/stop")
def monitor_stop():
    flash("Dauerempfang wurde beendet." if stop_monitor()
          else "Dauerempfang war nicht aktiv.", "success")
    return redirect(url_for("index"))


@app.get("/vehicle-signal/<profile_id>/<name>")
def download_vehicle_signal(profile_id: str, name: str):
    if profile_id not in VEHICLE_PROFILES or not NAME_RE.fullmatch(name):
        abort(404)
    path = VEHICLE_SIGNALS / profile_id / f"{name}.sub"
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name,
                     mimetype="text/plain")


if __name__ == "__main__":
    if MONITOR_ENABLED.exists():
        start_monitor(persist=False)
    threading.Thread(target=monitor_watchdog, daemon=True, name="monitor-watchdog").start()
    app.run(host="0.0.0.0", port=8080, debug=False)
