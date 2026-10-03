#!/usr/bin/env python3
"""Continuously discover repeated 433 MHz signals and log reception events."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from profiles import REMOTE_PROFILE, profile_for

import rfcontrol


BASE = Path(__file__).resolve().parent
SIGNALS = BASE / "signals"
VEHICLE_SIGNALS = BASE / "vehicle-signals"
EVENTS = BASE / "events.jsonl"
EVENTS_ARCHIVE = BASE / "events.1.jsonl"
STATUS = BASE / "monitor-status.json"
SENDABLE_PROTOCOLS = {"Princeton", "SMC5326", "Nice FLO", "Ansonic", "Linear"}
MAX_EVENT_BYTES = 5 * 1024 * 1024
MIN_FREE_BYTES = 100 * 1024 * 1024


def write_status(started_at: str, last_signal: str | None = None,
                 mode: str = "remote", profile_id: str | None = None) -> None:
    previous = {}
    try:
        previous = json.loads(STATUS.read_text())
    except (OSError, ValueError):
        pass
    status = {
        "started_at": started_at,
        "heartbeat": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "last_signal": last_signal if last_signal is not None else previous.get("last_signal"),
        "last_signal_at": (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
                           if last_signal is not None else previous.get("last_signal_at")),
        "mode": mode,
        "profile_id": profile_id or REMOTE_PROFILE["id"],
    }
    temporary = STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, indent=2) + "\n")
    temporary.replace(STATUS)


def existing_match(candidate: dict, candidate_path: Path) -> str | None:
    durations = candidate.get("durations_us", [])
    for path in SIGNALS.glob("*.json"):
        if path == candidate_path:
            continue
        try:
            saved = json.loads(path.read_text())
            candidate_key = candidate.get("key")
            saved_key = saved.get("key")
            candidate_protocol = candidate.get("protocol", "RAW")
            saved_protocol = saved.get("protocol", "RAW")
            if candidate_key and saved_key and candidate_protocol != "RAW":
                # A different command on the same remote often changes only
                # one or two bits. It must become a separate sendable button,
                # not a duplicate event of the first button.
                if candidate_protocol == saved_protocol and candidate_key == saved_key:
                    return path.stem
                continue
            # RAW signals have no semantic key. Be deliberately stricter than
            # the jitter-tolerant clustering used within one recording.
            saved_durations = saved.get("durations_us", [])
            if len(saved_durations) == len(durations) and all(
                (a > 0) == (b > 0)
                and abs(abs(a) - abs(b)) <= max(100, int(max(abs(a), abs(b)) * 0.2))
                for a, b in zip(saved_durations, durations)
            ):
                return path.stem
        except (OSError, ValueError, TypeError):
            pass
    return None


def append_event(signal_name: str, data: dict, mode: str = "remote",
                 profile_id: str | None = None) -> None:
    if EVENTS.exists() and EVENTS.stat().st_size >= MAX_EVENT_BYTES:
        EVENTS_ARCHIVE.unlink(missing_ok=True)
        EVENTS.replace(EVENTS_ARCHIVE)
    event = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "signal": signal_name, "protocol": data.get("protocol", "RAW"),
        "key": data.get("key"),
        "mode": mode, "profile_id": profile_id or REMOTE_PROFILE["id"],
    }
    with EVENTS.open("a") as stream:
        stream.write(json.dumps(event) + "\n")


def next_remote_name() -> tuple[str, str]:
    number = 1
    while (SIGNALS / f"Fernbedienung_{number:03d}.json").exists():
        number += 1
    return f"Fernbedienung_{number:03d}", f"Fernbedienung {number}"


def parse_key(value) -> int | None:
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        return None


def related_remote(data: dict) -> tuple[str, list[str]] | None:
    """Find the same physical remote without assuming fixed command-bit positions."""
    protocol = data.get("protocol", "RAW")
    key = parse_key(data.get("key"))
    bits = data.get("bits")
    te = data.get("te_us")
    if protocol == "RAW" or key is None:
        return None
    for path in SIGNALS.glob("*.json"):
        try:
            saved = json.loads(path.read_text())
            saved_key = parse_key(saved.get("key"))
            if (saved.get("protocol") != protocol or saved.get("bits") != bits
                    or saved_key is None):
                continue
            saved_te = saved.get("te_us")
            if te and saved_te and abs(te - saved_te) > max(80, te * 0.25):
                continue
            # Static remote buttons commonly alter only a handful of command
            # bits. This also supports devices where those bits are not the
            # final nibble. With 24-bit identifiers, an accidental collision
            # between unrelated remotes at <=4 bits distance is unlikely.
            if (key ^ saved_key).bit_count() <= 4:
                remote = saved.get("remote_name")
                if not remote:
                    remote = f"{protocol.replace(' ', '')}{saved_key:X}"
                buttons = []
                for other_path in SIGNALS.glob("*.json"):
                    try:
                        other = json.loads(other_path.read_text())
                        if other.get("remote_name") == remote:
                            buttons.append(other.get("button_name") or other.get("name"))
                    except (OSError, ValueError, TypeError):
                        pass
                return remote, [button for button in buttons if button]
        except (OSError, ValueError, TypeError):
            pass
    return None


def automatic_name(data: dict) -> tuple[str, str]:
    relation = related_remote(data)
    if relation:
        remote, existing_buttons = relation
    else:
        remote = data.get("remote_name")
        existing_buttons = []
    button = data.get("button_name")
    if button in existing_buttons or not button:
        number = 1
        while f"Taste {number}" in existing_buttons:
            number += 1
        button = f"Taste {number}"
    if not remote:
        protocol = data.get("protocol", "RAW")
        key = parse_key(data.get("key"))
        if protocol != "RAW" and key is not None:
            remote = f"{protocol.replace(' ', '')}{key:X}"
        else:
            internal, display = next_remote_name()
            data["remote_name"] = display
            data["button_name"] = "Signal"
            return internal, display
    data["remote_name"] = remote
    data["button_name"] = button
    slug_button = str(button or "Signal").replace(" ", "_").replace("0x", "")
    base = f"{remote}_{slug_button}"
    candidate = base
    number = 2
    while (SIGNALS / f"{candidate}.json").exists():
        candidate = f"{base}_{number}"
        number += 1
    return candidate, str(button or "Signal")


def monitor(hours: float, window: float, mode: str = "remote",
            profile_id: str | None = None) -> None:
    profile = profile_for(mode, profile_id)
    SIGNALS.mkdir(exist_ok=True)
    if mode == "vehicle":
        (VEHICLE_SIGNALS / profile["id"]).mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + hours * 3600 if hours > 0 else None
    started_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    try:
        started_at = json.loads(STATUS.read_text()).get("started_at") or started_at
    except (OSError, ValueError):
        pass
    write_status(started_at, mode=mode, profile_id=profile["id"])
    last_heartbeat = time.monotonic()
    print(f"Dauerempfang aktiv ({hours:g} h). Beenden mit Strg+C.", flush=True)
    while deadline is None or time.monotonic() < deadline:
        if shutil.disk_usage(BASE).free < MIN_FREE_BYTES:
            write_status(started_at, mode=mode, profile_id=profile["id"])
            print("Weniger als 100 MB frei; Empfang pausiert.", flush=True)
            time.sleep(60)
            continue
        if time.monotonic() - last_heartbeat >= 60:
            write_status(started_at, mode=mode, profile_id=profile["id"])
            last_heartbeat = time.monotonic()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if mode == "vehicle":
            raw_path = VEHICLE_SIGNALS / profile["id"] / f"vehicle_{stamp}.sub"
            result = subprocess.run(
                [sys.executable, str(BASE / "rfcontrol.py"), "record-vehicle",
                 raw_path.stem, "--seconds", str(window), "--profile", profile["id"]],
                cwd=BASE, text=True, capture_output=True, check=False,
            )
            if result.returncode == 0 and raw_path.exists():
                event = {
                    "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                    "signal": raw_path.stem, "protocol": profile["protocol"],
                    "key": None, "mode": mode, "profile_id": profile["id"],
                }
                if EVENTS.exists() and EVENTS.stat().st_size >= MAX_EVENT_BYTES:
                    EVENTS_ARCHIVE.unlink(missing_ok=True)
                    EVENTS.replace(EVENTS_ARCHIVE)
                with EVENTS.open("a") as stream:
                    stream.write(json.dumps(event) + "\n")
                write_status(started_at, raw_path.stem, mode, profile["id"])
                print(f"{datetime.now():%H:%M:%S} empfangen: {profile['protocol']} RAW",
                      flush=True)
            else:
                print(f"{datetime.now():%H:%M:%S} kein passendes Signal im Fenster",
                      flush=True)
            time.sleep(0.4)
            continue

        temporary_name = f"auto_{stamp}"
        result = subprocess.run(
            [sys.executable, str(BASE / "rfcontrol.py"), "record", temporary_name,
             "--seconds", str(window), "--no-debug"],
            cwd=BASE, text=True, capture_output=True, check=False,
        )
        debug_path = SIGNALS / ".debug" / f"{temporary_name}.json"
        if debug_path.exists():
            debug_path.unlink()
        path = SIGNALS / f"{temporary_name}.json"
        if result.returncode == 0 and path.exists():
            data = json.loads(path.read_text())
            if data.get("protocol", "RAW") not in SENDABLE_PROTOCOLS:
                # Repeated RAW traffic may be a weather station, sensor,
                # doorbell or an unsupported/rolling protocol. Keep the event
                # visible, but do not expose it as a replayable remote button.
                path.unlink()
                append_event("Unbekanntes RAW-Signal", data)
                write_status(started_at, "Unbekanntes RAW-Signal", mode, profile["id"])
                print(f"{datetime.now():%H:%M:%S} empfangen: RAW (nicht gespeichert)",
                      flush=True)
                time.sleep(0.4)
                continue
            matched = existing_match(data, path)
            if matched:
                path.unlink()
                signal_name = matched
            else:
                signal_name, display_name = automatic_name(data)
                destination = SIGNALS / f"{signal_name}.json"
                data["name"] = display_name
                data["auto_named"] = True
                destination.write_text(json.dumps(data, indent=2) + "\n")
                path.unlink()
            append_event(signal_name, data, mode, profile["id"])
            write_status(started_at, signal_name, mode, profile["id"])
            print(f"{datetime.now():%H:%M:%S} empfangen: {signal_name}", flush=True)
        time.sleep(0.4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=24,
                        help="Laufzeit in Stunden; 0 bedeutet unbegrenzt")
    parser.add_argument("--window", type=float, default=4,
                        help="Laenge eines Empfangsfensters in Sekunden")
    parser.add_argument("--mode", choices=("remote", "vehicle"), default="remote")
    parser.add_argument("--profile", default=REMOTE_PROFILE["id"])
    args = parser.parse_args()
    monitor(args.hours, args.window, args.mode, args.profile)
