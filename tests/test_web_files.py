"""Exercise file downloads and deletion without radio hardware."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import webapp
from profiles import VEHICLE_PROFILES, vehicle_capture_name


class WebFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.signals = root / "signals"
        self.vehicles = root / "vehicle-signals"
        self.signals.mkdir()
        self.vehicles.mkdir()
        for name, value in (("SIGNALS", self.signals), ("VEHICLE_SIGNALS", self.vehicles)):
            patcher = patch.object(webapp, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        webapp.app.config["TESTING"] = True
        self.client = webapp.app.test_client()

    def vehicle(self, name="vehicle_20261003_153000"):
        folder = self.vehicles / "vag-434-am"
        folder.mkdir(exist_ok=True)
        for suffix, contents in ((".sub", "original raw capture\n"), (".json", "{}"),
                                 (".edges.json", "[]")):
            (folder / f"{name}{suffix}").write_text(contents)
        return folder, name

    def test_remote_download_exports_waveform_with_repeats_and_idle_gap(self):
        values = [-200, 300, -900, 900, -300]
        path = self.signals / "remote_button.json"
        path.write_text(json.dumps({"durations_us": values, "repeats": 3,
                                    "frequency_hz": 433920000}))
        original = path.read_bytes()
        response = self.client.get("/remote-signal/remote_button")
        self.assertEqual(response.status_code, 200)
        self.assertIn("remote_button.sub", response.headers["Content-Disposition"])
        text = response.get_data(as_text=True)
        self.assertIn("Filetype: Flipper SubGhz RAW File", text)
        self.assertIn("Preset: FuriHalSubGhzPresetOok650Async", text)
        self.assertIn("Frequency: 433920000", text)
        exported = [int(value) for line in text.splitlines() if line.startswith("RAW_Data:")
                    for value in line.split(":", 1)[1].split()]
        self.assertEqual(exported, [300, -900, 900, -10300] * 3)
        self.assertEqual(path.read_bytes(), original)

    def test_invalid_remote_data_and_unknown_names_do_not_export(self):
        for data in ({}, {"durations_us": []}, {"durations_us": [True, -100]},
                     {"durations_us": [-100, -200]}, {"durations_us": [100, 0]}):
            (self.signals / "bad.json").write_text(json.dumps(data))
            self.assertEqual(self.client.get("/remote-signal/bad").status_code, 422)
        self.assertEqual(self.client.get("/remote-signal/missing").status_code, 404)
        self.assertEqual(self.client.get("/remote-signal/..%2Foutside").status_code, 404)

    def test_legacy_vehicle_download_uses_profile_name_and_original_data(self):
        folder, name = self.vehicle()
        response = self.client.get(f"/vehicle-signal/vag-434-am/{name}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("VAG_20261003_153000.sub", response.headers["Content-Disposition"])
        self.assertEqual(response.get_data(as_text=True), "original raw capture\n")
        self.assertTrue((folder / f"{name}.sub").exists())
        response.close()
        loaded = webapp.load_vehicle_signals()
        self.assertEqual(loaded[0]["display_name"], "VAG_20261003_153000")
        self.assertEqual(loaded[0]["name"], name)

    def test_vehicle_deletion_removes_only_selected_capture_and_sidecars(self):
        folder, name = self.vehicle()
        self.vehicle("VAG_other")
        route = f"/vehicle-signal/vag-434-am/{name}/delete"
        self.assertEqual(self.client.get(route).status_code, 405)
        self.assertTrue((folder / f"{name}.sub").exists())
        self.assertEqual(self.client.post(route).status_code, 302)
        for suffix in (".sub", ".json", ".edges.json"):
            self.assertFalse((folder / f"{name}{suffix}").exists())
            self.assertTrue((folder / f"VAG_other{suffix}").exists())
        self.assertEqual(self.client.post(route).status_code, 302)
        self.assertEqual(self.client.post("/vehicle-signal/unknown/VAG_other/delete").status_code, 404)
        self.assertTrue((folder / "VAG_other.sub").exists())

    def test_all_profiles_produce_safe_names_and_vag_prefix(self):
        import re
        for profile in VEHICLE_PROFILES.values():
            name = vehicle_capture_name(profile, "vehicle_20261003_153000")
            self.assertRegex(name, re.compile(r"^[a-zA-Z0-9_-]{1,48}$"))
            self.assertFalse(name.startswith("vehicle_"))
        self.assertEqual(vehicle_capture_name(VEHICLE_PROFILES["vag-434-am"],
                                             "vehicle_20261003_153000"), "VAG_20261003_153000")

    def test_controls_render_in_both_receive_modes(self):
        folder, name = self.vehicle()
        (self.signals / "remote_button.json").write_text(json.dumps({
            "durations_us": [300, -900], "name": "Button", "protocol": "RAW"}))
        signals = webapp.load_signals()
        for mode in ("remote", "vehicle"):
            with webapp.app.test_request_context("/"):
                rendered = webapp.render_template("index.html", signals=signals,
                    groups=webapp.group_signals(signals), events=[],
                    vehicle_signals=webapp.load_vehicle_signals(),
                    vehicle_profile_groups=webapp.grouped_vehicle_profiles(),
                    selected={"mode": mode, "profile_id": "vag-434-am"},
                    monitoring=False, status={})
            self.assertIn("/remote-signal/remote_button", rendered)
            self.assertIn(f"/vehicle-signal/vag-434-am/{name}/delete", rendered)
            self.assertIn("VAG_20261003_153000", rendered)
            self.assertIn("/delete/remote_button", rendered)


if __name__ == "__main__":
    unittest.main()
