"""CC1101 receive profiles based on ProtoPirate protocol/preset tables.

Profiles describe protocol families and RF settings. They are not a vehicle
model/year compatibility database.
"""

import re
import unicodedata


REMOTE_PROFILE = {
    "id": "remote-433-ook",
    "label": "Funkfernbedienungen · 433,92 MHz OOK",
    "make": "Funkfernbedienungen",
    "protocol": "Festcode-Profile",
    "frequency_hz": 433_920_000,
    "frequency_label": "433,92 MHz",
    "modulation": "OOK / AM",
    "encoding": "automatische Erkennung einfacher Festcode-Rahmen",
    "preset": "FuriHalSubGhzPresetOok650Async",
    "radio_preset": "remote",
    "kind": "remote",
}


def _profile(profile_id: str, make: str, protocol: str, frequency_hz: int,
             modulation: str, encoding: str, preset: str,
             radio_preset: str, custom_preset_data: str | None = None) -> dict:
    return {
        "id": profile_id,
        "make": make,
        "protocol": protocol,
        "label": f"{make} · {protocol}",
        "frequency_hz": frequency_hz,
        "frequency_label": f"{frequency_hz / 1_000_000:.2f} MHz".replace(".", ","),
        "modulation": modulation,
        "encoding": encoding,
        "preset": preset,
        "radio_preset": radio_preset,
        "custom_preset_data": custom_preset_data,
        "kind": "vehicle",
    }


AM = "FuriHalSubGhzPresetOok650Async"
FM = "FuriHalSubGhzPreset2FSKDev476Async"
AM650 = ("AM650", "AM/OOK", AM)
FM476 = ("FM476", "2-FSK", FM)

# ProtoPirate's Honda1 receiver configuration, exported in Flipper's custom
# CC1101 preset format. The Pi remaps only the GDO pins for its existing wiring.
HONDA1_CUSTOM = (
    "02 0D 0B 06 08 32 07 04 14 00 13 02 12 07 11 36 10 E9 "
    "15 32 18 18 19 16 1D 92 1C 40 1B 03 20 FB 22 10 21 56 "
    "00 00 C0 00 00 00 00 00 00 00"
)

VEHICLE_PROFILES = {
    "chrysler-v0-am433": _profile("chrysler-v0-am433", "Chrysler", "V0 · AM650",
        433_920_000, "AM/OOK", "PWM", AM, "AM650"),
    "fiat-v0-am433": _profile("fiat-v0-am433", "Fiat", "V0 · AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "fiat-v1-am433": _profile("fiat-v1-am433", "Fiat", "V1 · AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "fiat-v2-am433": _profile("fiat-v2-am433", "Fiat", "V2 · AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "ford-v0-am433": _profile("ford-v0-am433", "Ford", "V0 · AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "ford-v1-f4-433": _profile("ford-v1-f4-433", "Ford", "V1 · F4",
        433_920_000, "F4 / 2-FSK 47,6 kHz", "Manchester", FM, "FM476"),
    "ford-v2-f4-434": _profile("ford-v2-f4-434", "Ford", "V2 · F4",
        434_250_000, "F4 / 2-FSK 47,6 kHz", "Manchester", FM, "FM476"),
    "ford-v3-f4-434": _profile("ford-v3-f4-434", "Ford", "V3 · F4",
        434_250_000, "F4 / 2-FSK 47,6 kHz", "Manchester", FM, "FM476"),
    "honda-v1-am433": _profile("honda-v1-am433", "Honda", "V1 · AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "honda-static-433": _profile("honda-static-433", "Honda", "Static · Honda1",
        433_650_000, "Honda1 (Custom)", "PWM", "FuriHalSubGhzPresetCustom",
        "HONDA1", HONDA1_CUSTOM),
    "honda-v0-fm433": _profile("honda-v0-fm433", "Honda", "V0 · FM476",
        433_920_000, "FM476 / 2-FSK", "PWM", FM, "FM476"),
    "honda-v2-f4-433": _profile("honda-v2-f4-433", "Honda", "V2 · F4",
        433_920_000, "F4 / 2-FSK 47,6 kHz", "PWM", FM, "FM476"),
    "kia-v1-am433": _profile("kia-v1-am433", "Kia", "V1 · AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "kia-v0-fm433": _profile("kia-v0-fm433", "Kia", "V0 · FM476",
        433_920_000, "FM476 / 2-FSK", "PWM", FM, "FM476"),
    "kia-v2-fm433": _profile("kia-v2-fm433", "Kia", "V2 · FM476",
        433_920_000, "FM476 / 2-FSK", "Manchester", FM, "FM476"),
    "kia-v3-v4-fm433": _profile("kia-v3-v4-fm433", "Kia", "V3 / V4 · FM476",
        433_920_000, "FM476 / 2-FSK", "PWM", FM, "FM476"),
    "kia-v5-fm433": _profile("kia-v5-fm433", "Kia", "V5 · FM476",
        433_920_000, "FM476 / 2-FSK", "PWM", FM, "FM476"),
    "kia-v6-fm433": _profile("kia-v6-fm433", "Kia", "V6 · FM476",
        433_920_000, "FM476 / 2-FSK", "Manchester", FM, "FM476"),
    "kia-v7-fm433": _profile("kia-v7-fm433", "Kia", "V7 · FM476",
        433_920_000, "FM476 / 2-FSK", "Manchester", FM, "FM476"),
    "mazda-v0-am433": _profile("mazda-v0-am433", "Mazda", "V0 · AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "mitsubishi-v0-fm433": _profile("mitsubishi-v0-fm433", "Mitsubishi", "V0 · FM476",
        433_920_000, "FM476 / 2-FSK", "PWM", FM, "FM476"),
    "psa-am433": _profile("psa-am433", "Peugeot / Citroën", "AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "renault-v0-am433": _profile("renault-v0-am433", "Renault", "V0 · AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "renault-v1-am433": _profile("renault-v1-am433", "Renault", "V1 · AM650",
        433_920_000, "AM/OOK", "Manchester", AM, "AM650"),
    "starline-am433": _profile("starline-am433", "StarLine", "AM650",
        433_920_000, "AM/OOK", "PWM", AM, "AM650"),
    "subaru-am433": _profile("subaru-am433", "Subaru", "AM650",
        433_920_000, "AM/OOK", "PPM", AM, "AM650"),
    "suzuki-v0-fm433": _profile("suzuki-v0-fm433", "Suzuki", "V0 · FM476",
        433_920_000, "FM476 / 2-FSK", "PWM", FM, "FM476"),
    "vag-434-am": _profile("vag-434-am", "VW / Audi / Seat / Skoda", "VAG · AM650",
        434_420_000, "AM/OOK", "Manchester", AM, "AM650"),
}


def profile_for(mode: str, profile_id: str | None = None) -> dict:
    if mode == "remote":
        return REMOTE_PROFILE
    if mode == "vehicle" and profile_id in VEHICLE_PROFILES:
        return VEHICLE_PROFILES[profile_id]
    raise ValueError("Unbekanntes Empfangsprofil.")


def grouped_vehicle_profiles() -> list[dict]:
    groups: list[dict] = []
    indexed: dict[str, dict] = {}
    for profile in VEHICLE_PROFILES.values():
        group = indexed.get(profile["make"])
        if group is None:
            group = {"name": profile["make"], "profiles": []}
            indexed[profile["make"]] = group
            groups.append(group)
        group["profiles"].append(profile)
    return groups


def vehicle_capture_name(profile: dict, name: str) -> str:
    """Replace a generic vehicle filename with an ASCII profile prefix."""
    if not name.startswith("vehicle_"):
        return name
    protocol = profile["protocol"].split(" · ")[0]
    label = "VAG" if protocol == "VAG" else f"{profile['make']}_{protocol}"
    label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")[:28]
    return f"{prefix}_{name[len('vehicle_'):]}"
