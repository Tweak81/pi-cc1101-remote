"""Hardware-independent Flipper RAW export."""

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

