#!/usr/bin/env python3
"""Record and replay simple 433.92 MHz OOK remotes with a CC1101."""

from __future__ import annotations

import argparse
import fcntl
import json
import statistics
import sys
import time
from pathlib import Path

from profiles import profile_for

try:
    import pigpio
    import spidev
except ImportError as exc:
    raise SystemExit("Abhaengigkeit fehlt. Bitte zuerst ./install.sh ausfuehren.") from exc


FREQUENCY_HZ = 433_920_000
TX_GPIO = 24       # physical pin 18 -> module pin 3 / GDO0
RX_GPIO = 25       # physical pin 22 <- module pin 8 / GDO2
SIGNALS = Path(__file__).resolve().parent / "signals"
VEHICLE_SIGNALS = Path(__file__).resolve().parent / "vehicle-signals"
LOCK_PATH = "/tmp/pi-cc1101-remote.lock"


class HardwareLock:
    def __enter__(self):
        self.file = open(LOCK_PATH, "w")
        fcntl.flock(self.file, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_args):
        fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()


class CC1101:
    # Configuration registers
    IOCFG2, IOCFG0, FIFOTHR = 0x00, 0x02, 0x03
    PKTCTRL0, FSCTRL1 = 0x08, 0x0B
    FREQ2, FREQ1, FREQ0 = 0x0D, 0x0E, 0x0F
    MDMCFG4, MDMCFG3, MDMCFG2, MDMCFG1, MDMCFG0 = 0x10, 0x11, 0x12, 0x13, 0x14
    DEVIATN, MCSM0 = 0x15, 0x18
    FOCCFG, BSCFG = 0x19, 0x1A
    AGCCTRL2, AGCCTRL1, AGCCTRL0 = 0x1B, 0x1C, 0x1D
    FREND1, FREND0 = 0x21, 0x22
    FSCAL3, FSCAL2, FSCAL1, FSCAL0 = 0x23, 0x24, 0x25, 0x26
    TEST2, TEST1, TEST0 = 0x2C, 0x2D, 0x2E
    PARTNUM, VERSION = 0x30, 0x31
    PATABLE = 0x3E
    SRES, SRX, STX, SIDLE, SPWD = 0x30, 0x34, 0x35, 0x36, 0x39

    def __init__(self) -> None:
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 500_000
        self.spi.mode = 0

    def close(self) -> None:
        self.strobe(self.SIDLE)
        self.strobe(self.SPWD)
        self.spi.close()

    def strobe(self, command: int) -> int:
        return self.spi.xfer2([command])[0]

    def write(self, register: int, value: int) -> None:
        self.spi.xfer2([register, value])

    def write_burst(self, register: int, values: list[int]) -> None:
        self.spi.xfer2([register | 0x40, *values])

    def read_status(self, register: int) -> int:
        return self.spi.xfer2([register | 0xC0, 0])[1]

    def read_config(self, register: int) -> int:
        return self.spi.xfer2([register | 0x80, 0])[1]

    def reset_and_configure(self, frequency_hz: int = FREQUENCY_HZ,
                            radio_preset: str = "remote",
                            custom_preset_data: str | None = None) -> None:
        self.strobe(self.SRES)
        time.sleep(0.002)
        # 433.920 MHz, ASK/OOK, asynchronous serial mode. GDO2 is RX data;
        # in transmit mode GDO0 automatically becomes the serial data input.
        frequency_word = round(frequency_hz * (1 << 16) / 26_000_000)
        config = {
            # GDO2: asynchronous demodulated data; GDO0: carrier sense in RX.
            # In asynchronous TX mode GDO0 automatically becomes data input.
            self.IOCFG2: 0x0D, self.IOCFG0: 0x0E, self.FIFOTHR: 0x47,
            self.PKTCTRL0: 0x30, self.FSCTRL1: 0x06,
            self.FREQ2: (frequency_word >> 16) & 0xFF,
            self.FREQ1: (frequency_word >> 8) & 0xFF,
            self.FREQ0: frequency_word & 0xFF,
            # ~203 kHz receive bandwidth and ~4.8 kBaud. The previous 100
            # kBaud setting was much too fast for common fixed-code remotes.
            self.MDMCFG4: 0x87,
            self.MDMCFG3: 0x83, self.MDMCFG2: 0x30,
            self.DEVIATN: 0x15, self.MCSM0: 0x18,
            self.FOCCFG: 0x16, self.BSCFG: 0x6C,
            self.AGCCTRL2: 0x43, self.AGCCTRL1: 0x40, self.AGCCTRL0: 0x91,
            self.FREND1: 0x56, self.FREND0: 0x11,
            self.FSCAL3: 0xE9, self.FSCAL2: 0x2A, self.FSCAL1: 0x00,
            self.FSCAL0: 0x1F, self.TEST2: 0x81, self.TEST1: 0x35,
            self.TEST0: 0x09,
        }
        if radio_preset == "AM650":
            # Flipper's asynchronous OOK650 receive preset; GDO pins are
            # remapped below to match this Pi's GDO2-data/GDO0-carrier wiring.
            config.update({
                self.FIFOTHR: 0x07, self.PKTCTRL0: 0x32, self.FSCTRL1: 0x06,
                self.MDMCFG0: 0x00, self.MDMCFG1: 0x00,
                self.MDMCFG2: 0x30, self.MDMCFG3: 0x32, self.MDMCFG4: 0x17,
                self.FOCCFG: 0x18, self.AGCCTRL0: 0x91,
                self.AGCCTRL1: 0x00, self.AGCCTRL2: 0x07,
                self.FREND0: 0x11, self.FREND1: 0xB6,
            })
        elif radio_preset == "FM476":
            config.update({
                self.PKTCTRL0: 0x32, self.MDMCFG0: 0x00, self.MDMCFG1: 0x02,
                self.MDMCFG2: 0x04, self.MDMCFG3: 0x83, self.MDMCFG4: 0x67,
                self.DEVIATN: 0x47, self.FOCCFG: 0x16, self.AGCCTRL0: 0x91,
                self.AGCCTRL1: 0x00, self.AGCCTRL2: 0x07,
                self.FREND0: 0x10, self.FREND1: 0x56,
            })
        elif radio_preset == "HONDA1" and custom_preset_data:
            values = [int(value, 16) for value in custom_preset_data.split()]
            index = 0
            while index + 1 < len(values) and values[index:index + 2] != [0, 0]:
                config[values[index]] = values[index + 1]
                index += 2
        # Existing wiring uses GDO2 for asynchronous demodulated data and
        # GDO0 as carrier sense. Preserve the preset's modem settings above.
        config.update({self.IOCFG2: 0x0D, self.IOCFG0: 0x0E})
        for register, value in config.items():
            self.write(register, value)
        # ASK/OOK alternates between PATABLE entries 0 (carrier off) and 1
        # (carrier on). FREND0.PA_POWER=1 above selects both entries.
        # 0xC0 is the CC1101 data-sheet value for approximately +10 dBm at
        # 433 MHz; remaining entries are deliberately unused.
        self.write_burst(self.PATABLE, [0x00, 0xC0, 0, 0, 0, 0, 0, 0])

    def identity(self) -> tuple[int, int]:
        return self.read_status(self.PARTNUM), self.read_status(self.VERSION)


def connect_gpio() -> "pigpio.pi":
    pi = pigpio.pi()
    if not pi.connected:
        raise SystemExit("pigpiod laeuft nicht. Starte: sudo systemctl start pigpiod")
    return pi


def trim_capture(edges: list[tuple[int, int]], gap_us: int) -> list[list[int]]:
    """Turn edge timestamps into separate signed-duration frames."""
    if len(edges) < 3:
        return []
    frames: list[list[int]] = []
    current: list[int] = []
    for (level, tick), (_, next_tick) in zip(edges, edges[1:]):
        duration = pigpio.tickDiff(tick, next_tick)
        if duration >= gap_us:
            if len(current) >= 8:
                frames.append(current)
            current = []
        elif duration >= 40:
            current.append(duration if level else -duration)
    if len(current) >= 8:
        frames.append(current)
    return frames


def frames_match(left: list[int], right: list[int]) -> bool:
    """Accept jitter, but reject polarity, alignment and timing mismatches."""
    if len(left) != len(right):
        return False
    mismatches = 0
    for a, b in zip(left, right):
        if (a > 0) != (b > 0):
            return False
        difference = abs(abs(a) - abs(b))
        tolerance = max(180, int(max(abs(a), abs(b)) * 0.35))
        if difference > tolerance:
            mismatches += 1
    return mismatches <= max(1, len(left) // 12)


def choose_frame(frames: list[list[int]]) -> tuple[list[int], int]:
    # Normal fixed-code remotes repeat a complete frame several times while a
    # button is pressed. Random receiver noise does not repeat with the same
    # polarity, edge count and pulse timing.
    candidates = [frame for frame in frames if 20 <= len(frame) <= 400]
    clusters: list[list[list[int]]] = []
    for frame in candidates:
        for cluster in clusters:
            if frames_match(cluster[0], frame):
                cluster.append(frame)
                break
        else:
            clusters.append([frame])
    if not clusters:
        raise SystemExit(
            "Kein vollstaendiger Signalrahmen erkannt. Fernbedienung naeher an "
            "die Antenne halten und dieselbe Taste mehrfach druecken."
        )
    best = max(clusters, key=len)
    if len(best) < 3:
        raise SystemExit(
            "Nur Rauschen bzw. kein mindestens dreimal wiederholtes Muster erkannt. "
            "Abstand variieren und dieselbe Taste laenger oder haeufiger druecken."
        )
    averaged = [round(statistics.median(values)) for values in zip(*best)]
    return averaged, len(best)


def decode_protocol(durations: list[int]) -> dict:
    """Best-effort decoder for common static OOK pulse-width protocols."""
    for offset in (0, 1):
        values = durations[offset:]
        pairs = list(zip(values[0::2], values[1::2]))
        if not 8 <= len(pairs) <= 64:
            continue
        short_values = [min(abs(a), abs(b)) for a, b in pairs]
        te = round(statistics.median(short_values))
        if not 100 <= te <= 1000:
            continue
        bits = []
        valid = 0
        for first, second in pairs:
            a, b = abs(first), abs(second)
            if a <= te * 1.8 and 1.7 * te <= b <= 4.8 * te:
                bits.append("0"); valid += 1
            elif b <= te * 1.8 and 1.7 * te <= a <= 4.8 * te:
                bits.append("1"); valid += 1
            else:
                bits.append("?")
        if valid / len(pairs) >= 0.9 and "?" not in bits:
            bit_string = "".join(bits)
            key = int(bit_string, 2)
            bit_count = len(bit_string)
            protocol = None
            aliases = []
            if bit_count == 24 and 120 <= te <= 700:
                protocol = "Princeton"
                aliases = ["EV1527", "PT2262-compatible"]
            elif bit_count == 25 and 180 <= te <= 500:
                protocol = "SMC5326"
            elif bit_count == 12 and 550 <= te <= 900:
                protocol = "Nice FLO"
            elif bit_count == 12 and 350 <= te < 550:
                protocol = "Ansonic"
            elif bit_count == 10 and 350 <= te <= 700:
                protocol = "Linear"
            if protocol is None:
                continue
            decoded = {
                "protocol": protocol, "bits": bit_count,
                "key": f"0x{key:0{(len(bit_string) + 3) // 4}X}",
                "te_us": te,
            }
            if aliases:
                decoded["compatible_protocols"] = aliases
            if protocol == "Princeton":
                remote_id = key >> 4
                command = key & 0xF
                button_map = {1: 1, 2: 2, 4: 3, 8: 4}
                button = button_map.get(command)
                decoded.update({
                    "remote_id": f"{remote_id:05X}",
                    "command": f"0x{command:X}",
                    "remote_name": f"Princeton{remote_id:05X}",
                    "button_name": f"Taste {button}" if button else f"Taste 0x{command:X}",
                })
            else:
                decoded.update({
                    "remote_id": f"{key:X}",
                    "remote_name": f"{protocol.replace(' ', '')}{key:X}",
                    "button_name": "Signal",
                })
            return decoded
    return {"protocol": "RAW"}


def record(name: str, seconds: float, gap_us: int, save_debug: bool = True) -> None:
    radio, pi = CC1101(), connect_gpio()
    edges: list[tuple[int, int]] = []
    carrier_active = [False]
    try:
        radio.reset_and_configure()
        pi.set_mode(RX_GPIO, pigpio.INPUT)
        pi.set_mode(TX_GPIO, pigpio.INPUT)
        pi.set_glitch_filter(RX_GPIO, 40)
        pi.set_glitch_filter(TX_GPIO, 80)

        def carrier(_gpio: int, level: int, _tick: int) -> None:
            if level in (0, 1):
                carrier_active[0] = bool(level)

        def edge(_gpio: int, level: int, tick: int) -> None:
            if level in (0, 1) and carrier_active[0]:
                edges.append((level, tick))

        carrier_callback = pi.callback(TX_GPIO, pigpio.EITHER_EDGE, carrier)
        callback = pi.callback(RX_GPIO, pigpio.EITHER_EDGE, edge)
        radio.strobe(radio.SRX)
        print(f"Jetzt Taste mehrfach druecken ({seconds:.0f} Sekunden Aufnahme) ...")
        time.sleep(seconds)
        callback.cancel()
        carrier_callback.cancel()
        radio.strobe(radio.SIDLE)
        frames = trim_capture(edges, gap_us)
        SIGNALS.mkdir(exist_ok=True)
        if save_debug:
            debug_dir = SIGNALS / ".debug"
            debug_dir.mkdir(exist_ok=True)
            (debug_dir / f"{name}.json").write_text(json.dumps(frames, indent=2) + "\n")
        frame, matched_frames = choose_frame(frames)
        payload = {
            "name": name, "frequency_hz": FREQUENCY_HZ,
            "durations_us": frame, "repeats": 8,
            "captured_frames": len(frames), "matched_frames": matched_frames,
            **decode_protocol(frame),
        }
        (SIGNALS / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(f"Gespeichert: {name} ({len(frame)} Impulse, "
              f"{matched_frames} passende Wiederholungen aus {len(frames)} Kandidaten)")
    finally:
        pi.stop()
        radio.close()


def raw_sub_text(profile: dict, durations: list[int]) -> str:
    lines = [
        "Filetype: Flipper SubGhz RAW File",
        "Version: 1",
        f"Frequency: {profile['frequency_hz']}",
        f"Preset: {profile['preset']}",
    ]
    if profile.get("custom_preset_data"):
        lines.extend([
            "Custom_preset_module: CC1101",
            f"Custom_preset_data: {profile['custom_preset_data']}",
        ])
    lines.append("Protocol: RAW")
    for offset in range(0, len(durations), 512):
        lines.append("RAW_Data: " + " ".join(str(value) for value in durations[offset:offset + 512]))
    return "\n".join(lines) + "\n"


def record_vehicle(name: str, seconds: float, profile_id: str, save_debug: bool = False) -> None:
    """Passively capture a configured vehicle-family profile to Flipper RAW."""
    profile = profile_for("vehicle", profile_id)
    radio, pi = CC1101(), connect_gpio()
    edges: list[tuple[int, int]] = []
    carrier_active = [False]
    try:
        radio.reset_and_configure(profile["frequency_hz"], profile["radio_preset"],
                                  profile.get("custom_preset_data"))
        pi.set_mode(RX_GPIO, pigpio.INPUT)
        pi.set_mode(TX_GPIO, pigpio.INPUT)
        pi.set_glitch_filter(RX_GPIO, 40)
        pi.set_glitch_filter(TX_GPIO, 80)

        def carrier(_gpio: int, level: int, _tick: int) -> None:
            if level in (0, 1):
                carrier_active[0] = bool(level)

        def edge(_gpio: int, level: int, tick: int) -> None:
            if level in (0, 1) and carrier_active[0]:
                edges.append((level, tick))

        carrier_callback = pi.callback(TX_GPIO, pigpio.EITHER_EDGE, carrier)
        callback = pi.callback(RX_GPIO, pigpio.EITHER_EDGE, edge)
        radio.strobe(radio.SRX)
        print(f"Passiver RAW-Empfang: {profile['label']} ({seconds:.0f} s) ...", flush=True)
        time.sleep(seconds)
        callback.cancel()
        carrier_callback.cancel()
        radio.strobe(radio.SIDLE)

        frames = trim_capture(edges, 8_000)
        durations: list[int] = []
        for frame in frames:
            # The Flipper RAW reader requires the first duration to be positive.
            start = next((i for i, value in enumerate(frame) if value > 0), len(frame))
            frame = frame[start:]
            if len(frame) < 8:
                continue
            if durations and durations[-1] > 0:
                durations.append(-8_000)
            for value in frame:
                if durations and (durations[-1] > 0) == (value > 0):
                    durations[-1] += value
                else:
                    durations.append(value)

        if len(durations) < 20:
            raise SystemExit("Im Aufnahmefenster wurde kein ausreichend langes Signal erkannt.")
        folder = VEHICLE_SIGNALS / profile_id
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / f"{name}.sub"
        destination.write_text(raw_sub_text(profile, durations))
        details = {
            "name": name, "profile_id": profile_id, "protocol_family": profile["protocol"],
            "vehicle_group": profile["make"], "frequency_hz": profile["frequency_hz"],
            "modulation": profile["modulation"], "encoding": profile["encoding"],
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "duration_seconds": seconds, "timing_count": len(durations),
            "passive_capture": True,
        }
        destination.with_suffix(".json").write_text(json.dumps(details, indent=2) + "\n")
        if save_debug:
            debug = folder / f"{name}.edges.json"
            debug.write_text(json.dumps(edges) + "\n")
        print(f"Gespeichert: {destination} ({len(durations)} Zeitwerte)", flush=True)
    finally:
        pi.stop()
        radio.close()


def send(name: str, repeats: int | None, invert: bool) -> None:
    path = SIGNALS / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"Signal nicht gefunden: {name}")
    signal = json.loads(path.read_text())
    durations = signal["durations_us"]
    count = repeats or int(signal.get("repeats", 8))
    radio, pi = CC1101(), connect_gpio()
    try:
        radio.reset_and_configure()
        pi.set_mode(TX_GPIO, pigpio.OUTPUT)
        pi.write(TX_GPIO, 0)
        pulses = []
        mask = 1 << TX_GPIO
        for signed_duration in durations:
            high = signed_duration > 0
            if invert:
                high = not high
            pulses.append(pigpio.pulse(mask if high else 0, 0 if high else mask,
                                       abs(int(signed_duration))))
        # A conservative inter-frame pause used by many fixed-code remotes.
        pulses.append(pigpio.pulse(0, mask, 10_000))
        pi.wave_add_generic(pulses)
        wave = pi.wave_create()
        if wave < 0:
            raise SystemExit("GPIO-Wellenform konnte nicht erstellt werden")
        radio.strobe(radio.STX)
        time.sleep(0.002)
        for _ in range(count):
            pi.wave_send_once(wave)
            while pi.wave_tx_busy():
                time.sleep(0.001)
        radio.strobe(radio.SIDLE)
        pi.wave_delete(wave)
        print(f"Gesendet: {name} ({count} Wiederholungen)")
    finally:
        pi.write(TX_GPIO, 0)
        pi.stop()
        radio.close()


def diagnose() -> None:
    radio = CC1101()
    try:
        radio.reset_and_configure()
        part, version = radio.identity()
        print(f"CC1101 PARTNUM=0x{part:02X}, VERSION=0x{version:02X}")
        checks = {
            "IOCFG2": (radio.IOCFG2, 0x0D),
            "IOCFG0": (radio.IOCFG0, 0x0E),
            "FREQ2": (radio.FREQ2, 0x10),
            "MDMCFG4": (radio.MDMCFG4, 0x87),
            "MDMCFG3": (radio.MDMCFG3, 0x83),
            "MDMCFG2": (radio.MDMCFG2, 0x30),
        }
        matches = 0
        for label, (register, expected) in checks.items():
            actual = radio.read_config(register)
            print(f"{label}: gelesen=0x{actual:02X}, erwartet=0x{expected:02X}")
            matches += actual == expected
        pa0 = radio.spi.xfer2([radio.PATABLE | 0xC0, 0, 0])[1:]
        print(f"PATABLE[0:2]: gelesen=0x{pa0[0]:02X},0x{pa0[1]:02X}, "
              "erwartet=0x00,0xC0")
        matches += pa0 == [0x00, 0xC0]
        if matches != len(checks) + 1:
            raise SystemExit(
                "SPI-Schreib-/Lesetest fehlgeschlagen. Besonders CSN, SCK, MOSI "
                "und MISO sowie die spiegelverkehrte Ansicht der Stiftleiste pruefen."
            )
        if part != 0x00 or version not in (0x04, 0x14, 0x17):
            print("Warnung: ungewoehnliche Chipkennung, aber SPI-Schreib-/Lesetest ist OK.")
        print("SPI-Verbindung sieht gut aus.")
    finally:
        radio.close()


def list_signals() -> None:
    SIGNALS.mkdir(exist_ok=True)
    files = sorted(SIGNALS.glob("*.json"))
    print("\n".join(p.stem for p in files) if files else "Noch keine Signale gespeichert.")


def analyze_signals() -> None:
    updated = 0
    for path in SIGNALS.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            decoded = decode_protocol(data.get("durations_us", []))
            for key in ("protocol", "bits", "key", "te_us", "compatible_protocols",
                        "remote_id", "command", "remote_name", "button_name"):
                data.pop(key, None)
            data.update(decoded)
            if (data.get("name", "").startswith("Fernbedienung ")
                    and decoded.get("remote_name")):
                data["name"] = decoded["button_name"]
                data["auto_named"] = True
            path.write_text(json.dumps(data, indent=2) + "\n")
            updated += 1
        except (OSError, ValueError, TypeError):
            print(f"Uebersprungen: {path.name}", file=sys.stderr)
    print(f"{updated} gespeicherte Signale analysiert.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("diagnose")
    commands.add_parser("list")
    commands.add_parser("analyze")
    rec = commands.add_parser("record")
    rec.add_argument("name")
    rec.add_argument("--seconds", type=float, default=10)
    rec.add_argument("--gap-us", type=int, default=8_000)
    rec.add_argument("--no-debug", action="store_true",
                     help="keine Rohkandidaten speichern (fuer Dauerbetrieb)")
    vehicle = commands.add_parser("record-vehicle")
    vehicle.add_argument("name")
    vehicle.add_argument("--profile", required=True)
    vehicle.add_argument("--seconds", type=float, default=4)
    vehicle.add_argument("--debug", action="store_true")
    tx = commands.add_parser("send")
    tx.add_argument("name")
    tx.add_argument("--repeats", type=int)
    tx.add_argument("--invert", action="store_true")
    args = parser.parse_args()
    if args.command in ("list", "analyze"):
        list_signals() if args.command == "list" else analyze_signals()
    else:
        with HardwareLock():
            if args.command == "diagnose": diagnose()
            elif args.command == "record":
                record(args.name, args.seconds, args.gap_us, not args.no_debug)
            elif args.command == "record-vehicle":
                record_vehicle(args.name, args.seconds, args.profile, args.debug)
            elif args.command == "send": send(args.name, args.repeats, args.invert)


if __name__ == "__main__":
    main()
