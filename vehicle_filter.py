"""Conservative receive-only vehicle-frame plausibility filtering.

The timing values and minimum frame lengths are based on ProtoPirate's
published decoder timing table. A match is a protocol-shaped candidate, not
proof of which physical transmitter sent it.
"""

from __future__ import annotations

from collections import Counter


# short TE, long TE, decoder tolerance, minimum decoded bits, encoding
# Values mirror protocols/protocol_timings.c in ProtoPirate.
SPECS = {
    "chrysler-v0-am433": (300, 3700, 400, 80, "PWM"),
    "fiat-v0-am433": (200, 400, 100, 64, "Manchester"),
    "fiat-v1-am433": (250, 500, 100, 102, "Manchester"),
    "fiat-v2-am433": (210, 420, 100, 112, "Manchester"),
    "ford-v0-am433": (250, 500, 100, 64, "Manchester"),
    "ford-v1-f4-433": (65, 130, 39, 136, "Manchester"),
    "ford-v2-f4-434": (200, 400, 260, 104, "Manchester"),
    "ford-v3-f4-434": (240, 480, 60, 104, "Manchester"),
    "honda-v1-am433": (1000, 2000, 400, 64, "Manchester"),
    "honda-static-433": (63, 700, 120, 64, "PWM"),
    "honda-v0-fm433": (250, 500, 100, 61, "PWM"),
    "honda-v2-f4-433": (250, 500, 100, 81, "PWM"),
    "kia-v1-am433": (800, 1600, 200, 56, "Manchester"),
    "kia-v0-fm433": (250, 500, 100, 61, "PWM"),
    "kia-v2-fm433": (500, 1000, 150, 51, "Manchester"),
    "kia-v3-v4-fm433": (400, 800, 150, 64, "PWM"),
    "kia-v5-fm433": (400, 800, 150, 64, "PWM"),
    "kia-v6-fm433": (200, 400, 100, 144, "Manchester"),
    "kia-v7-fm433": (250, 500, 100, 64, "Manchester"),
    "mazda-v0-am433": (250, 500, 100, 64, "Manchester"),
    "mitsubishi-v0-fm433": (250, 500, 100, 61, "PWM"),
    "psa-am433": (250, 500, 100, 128, "Manchester"),
    "renault-v0-am433": (125, 250, 60, 82, "Manchester"),
    "renault-v1-am433": (125, 250, 50, 88, "Manchester"),
    "starline-am433": (250, 500, 120, 64, "PWM"),
    "subaru-am433": (800, 1600, 200, 64, "PPM"),
    "suzuki-v0-fm433": (250, 500, 100, 61, "PWM"),
}

_VAG_SPECS = ((300, 600), (500, 1000))


def _close(value: int, target: int, tolerance: int) -> bool:
    return abs(value - target) <= tolerance


def _vag_preamble(frame: list[int]) -> bool:
    """Check one of VAG's two documented framing patterns before data."""
    widths = [abs(value) for value in frame]
    # Type 1/2: >=151 short half-cells followed by a long marker.
    for offset in range(min(3, len(widths))):
        short_run = 0
        for width in widths[offset:]:
            if 200 <= width <= 400:
                short_run += 1
            else:
                break
        if short_run >= 151 and short_run < len(widths) - offset \
                and 400 <= widths[offset + short_run] <= 800:
            return True

    # Type 3/4: >=31 short half-cells, long marker, then three sync pairs.
    for offset in range(min(3, len(widths))):
        short_run = 0
        for width in widths[offset:]:
            if 400 <= width <= 600:
                short_run += 1
            else:
                break
        if short_run < 31 or short_run >= len(widths) - offset \
                or not 800 <= widths[offset + short_run] <= 1200:
            continue
        sync = widths[offset + short_run + 1:offset + short_run + 7]
        if len(sync) == 6 and all(600 <= width <= 900 for width in sync):
            return True
    return False


def _timing_score(frame: list[int], short: int, long: int, delta: int) -> tuple[float, int, int]:
    # Some published tables use very broad decoder deltas. Cap the matching
    # window so the short and long timing classes remain meaningfully distinct.
    tolerance = min(delta, max(45, int(short * 0.32)))
    long_tolerance = min(delta, max(60, int(long * 0.25)))
    matched = 0
    short_count = 0
    long_count = 0
    for signed in frame:
        width = abs(signed)
        if _close(width, short, tolerance):
            matched += 1
            short_count += 1
        elif _close(width, long, long_tolerance):
            matched += 1
            long_count += 1
    return matched / max(1, len(frame)), short_count, long_count


def _candidate(frame: list[int], profile_id: str) -> dict | None:
    if profile_id == "vag-434-am":
        if len(frame) < 100 or not _vag_preamble(frame):
            return None
        best = max((_timing_score(frame, short, long, 100) for short, long in _VAG_SPECS),
                   key=lambda item: item[0])
        if best[0] < 0.90 or best[1] + best[2] < 80:
            return None
        return {"score": best[0], "pulse_count": len(frame), "encoding": "Manchester"}

    spec = SPECS.get(profile_id)
    if spec is None:
        return None
    short, long, delta, min_bits, encoding = spec
    score, short_count, long_count = _timing_score(frame, short, long, delta)
    min_pulses = int(min_bits * (0.70 if encoding == "Manchester" else 0.85))
    min_score = 0.90 if encoding == "Manchester" else 0.94
    if len(frame) < min_pulses or score < min_score:
        return None
    if not short_count or not long_count:
        return None
    return {"score": score, "pulse_count": len(frame), "encoding": encoding}


def _similar_shape(left: list[int], right: list[int], profile_id: str) -> bool:
    if not 0.75 <= len(left) / max(1, len(right)) <= 1.33:
        return False
    spec = SPECS.get(profile_id)
    timing_pairs = _VAG_SPECS if profile_id == "vag-434-am" else ((spec[0], spec[1]),)
    def bucket_count(frame: list[int]) -> Counter:
        # Compare timing-class and signal-level distributions, allowing rolling
        # code payload bits to vary between consecutive transmissions.
        short, long = max(timing_pairs, key=lambda pair: sum(
            min(abs(abs(value) - pair[0]), abs(abs(value) - pair[1])) < max(80, pair[0] * .3)
            for value in frame))
        tolerance = max(80, short * .32)
        result = Counter()
        for value in frame:
            width = abs(value)
            if abs(width - short) <= tolerance:
                result[("short", value > 0)] += 1
            elif abs(width - long) <= max(100, long * .25):
                result[("long", value > 0)] += 1
        return result
    a, b = bucket_count(left), bucket_count(right)
    if not a or not b:
        return False
    total_a, total_b = sum(a.values()), sum(b.values())
    shared = sum(min(a[key] / total_a, b[key] / total_b) for key in a.keys() | b.keys())
    return shared >= 0.58


def validate_capture(frames: list[list[int]], profile_id: str) -> tuple[list[list[int]], dict]:
    """Return repeated high-likelihood frames, or raise a human-readable error."""
    candidates = [(frame, _candidate(frame, profile_id)) for frame in frames]
    candidates = [(frame, info) for frame, info in candidates if info]
    if len(candidates) < 2:
        raise ValueError("Kein wiederholter Rahmen mit passender Fahrzeug-Protokollstruktur erkannt.")

    clusters: list[list[tuple[list[int], dict]]] = []
    for frame, info in candidates:
        for cluster in clusters:
            if _similar_shape(cluster[0][0], frame, profile_id):
                cluster.append((frame, info))
                break
        else:
            clusters.append([(frame, info)])
    best = max(clusters, key=lambda cluster: (len(cluster), sum(item[1]["score"] for item in cluster)))
    if len(best) < 2:
        raise ValueError("Einzelner Treffer verworfen; mindestens zwei passende Wiederholungen nötig.")
    accepted = [frame for frame, _ in best]
    score = sum(info["score"] for _, info in best) / len(best)
    return accepted, {
        "validation": "wahrscheinlicher Fahrzeugprotokoll-Treffer",
        "validation_method": "decoder timing, Mindestlaenge und Wiederholung",
        "validation_score": round(score, 3),
        "validated_frames": len(accepted),
        "vehicle_origin_proven": False,
    }
