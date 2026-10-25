"""Authoring isolation, request contracts and secret handling without paid calls."""
import base64
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib import error

from tools import external_assets as assets


def brief(provider="meshy", **updates):
    value = {"id": "test-prop-v1", "provider": provider, "prompt": "A stone well",
             "license_note": "Review the plan and output before use."}
    if provider == "scenario":
        value["model"] = "model_owned_style"
    value.update(updates)
    return value


class ExternalAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(assets, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = assets.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def write_brief(self, value):
        path = self.root / "brief.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    def test_plan_and_doctor_are_offline_and_do_not_stage(self):
        with patch.object(assets.request, "build_opener", side_effect=AssertionError("HTTP forbidden")):
            path = self.write_brief(brief())
            self.assertEqual(self.run_cli("plan", "--brief", path)[0], 0)
            self.assertEqual(self.run_cli("doctor")[0], 0)
            self.assertNotEqual(self.run_cli("submit", "--brief", path)[0], 0)
        self.assertFalse((self.root / "scratch").exists())

    def test_provider_request_contracts(self):
        scenario = assets.build_plan(brief("scenario"))
        self.assertEqual(scenario["body"], {"prompt": "A stone well", "aspectRatio": "1:1"})
        self.assertEqual(scenario["endpoint"], "https://api.cloud.scenario.com/v1/generate/custom/model_owned_style")
        meshy = assets.build_plan(brief())
        self.assertEqual(meshy["body"]["mode"], "preview")
        self.assertEqual(meshy["body"]["target_formats"], ["glb"])
        sound = assets.build_plan(brief("elevenlabs", settings={"duration_seconds": 2, "loop": True}))
        self.assertEqual(sound["body"]["text"], "A stone well")
        self.assertTrue(sound["endpoint"].endswith("output_format=mp3_44100_128"))
        self.assertEqual(meshy, assets.build_plan(brief()))

    def test_invalid_briefs_and_bounds(self):
        cases = [brief(id="../escape"), brief(id="a" * 65), brief(provider="unknown"),
                 brief(prompt="x" * 801), brief(settings={"target_polycount": True}),
                 brief(settings={"target_polycount": 10**1000}),
                 brief("scenario", model="../escape"), brief("scenario", settings={"aspectRatio": []}),
                 brief("elevenlabs", settings={"duration_seconds": 31}),
                 brief("elevenlabs", settings={"prompt_influence": float("nan")}),
                 brief("elevenlabs", settings={"loop": 1}), brief(api_key="must-not-be-accepted")]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                assets.build_plan(value)

    def test_missing_credentials_do_not_write_or_request(self):
        with patch.dict(assets.os.environ, {}, clear=True), patch.object(assets, "_http") as http:
            with self.assertRaisesRegex(ValueError, "MESHY_API_KEY"):
                assets.execute(assets.build_plan(brief()))
            http.assert_not_called()
        self.assertFalse((self.root / "scratch").exists())

    def test_submit_records_are_sanitized_and_duplicate_is_blocked(self):
        secret = "secret-for-test-only"
        response = json.dumps({"result": "task-123", "echo": secret}).encode()
        with patch.dict(assets.os.environ, {"MESHY_API_KEY": secret}), patch.object(assets, "_http", return_value=(response, "application/json")) as http:
            result = assets.execute(assets.build_plan(brief()))
            self.assertEqual(result["task_id"], "task-123")
            with self.assertRaisesRegex(ValueError, "already"):
                assets.execute(assets.build_plan(brief()))
            self.assertEqual(http.call_count, 1)
        records = "".join(path.read_text() for path in (self.root / "scratch").rglob("*.json"))
        self.assertNotIn(secret, records)
        self.assertIn("[REDACTED]", records)

    def test_scenario_auth_and_poll_contract(self):
        key, secret = "example-key", "example-secret"
        token = base64.b64encode(f"{key}:{secret}".encode()).decode()
        response = {"job": {"jobId": "job_test", "status": "success"}, "echo": token}
        with patch.dict(assets.os.environ, {"SCENARIO_API_KEY": key, "SCENARIO_API_SECRET": secret}), patch.object(assets, "_http", return_value=(json.dumps(response).encode(), "application/json")) as http:
            result = assets.execute(assets.build_plan(brief("scenario")), action="status", task_id="job_test")
            args = http.call_args.args
            self.assertEqual(args[0], "https://api.cloud.scenario.com/v1/jobs/job_test")
            self.assertEqual(args[1], "GET")
            self.assertEqual(args[2]["Authorization"], "Basic " + token)
            self.assertEqual(result["status"], "success")
            self.assertNotIn(token, Path(result["record"]).read_text())

    def test_audio_is_staged_unreviewed_without_runtime_writes(self):
        with patch.dict(assets.os.environ, {"ELEVENLABS_API_KEY": "example-secret"}), patch.object(assets, "_http", return_value=(b"ID3test-audio", "audio/mpeg")):
            result = assets.execute(assets.build_plan(brief("elevenlabs")))
        folder = Path(result["record"]).parent
        self.assertEqual((folder / "unreviewed.mp3").read_bytes(), b"ID3test-audio")
        self.assertEqual(result["review_status"], "unreviewed")
        self.assertFalse((self.root / "worldseed").exists())

    def test_network_error_never_echoes_exception_payload_and_never_retries(self):
        secret = "do-not-print-this-token"
        opener = unittest.mock.MagicMock()
        opener.open.side_effect = error.URLError(secret)
        with patch.dict(assets.os.environ, {"MESHY_API_KEY": secret}), patch.object(assets.request, "build_opener", return_value=opener):
            code, out, err = self.run_cli("submit", "--brief", self.write_brief(brief()), "--execute")
        self.assertEqual(code, 2)
        self.assertNotIn(secret, out + err)
        self.assertEqual(opener.open.call_count, 1)

    def test_symlink_staging_is_rejected(self):
        outside = self.root / "runtime"
        outside.mkdir()
        try:
            (self.root / "scratch").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        with patch.dict(assets.os.environ, {"MESHY_API_KEY": "example-secret"}), patch.object(assets, "_http") as http:
            with self.assertRaisesRegex(ValueError, "symlinks"):
                assets.execute(assets.build_plan(brief()))
            http.assert_not_called()
        self.assertEqual(list(outside.iterdir()), [])

    def test_doctor_and_plan_output_hide_environment_values(self):
        secret = "example-secret-never-log"
        with patch.dict(assets.os.environ, {"MESHY_API_KEY": secret}):
            code, out, err = self.run_cli("doctor")
            self.assertEqual(code, 0)
            self.assertNotIn(secret, out + err)
            code, out, err = self.run_cli("plan", "--brief", self.write_brief(brief(prompt=secret)))
            self.assertEqual(code, 0)
            self.assertNotIn(secret, out + err)

    def test_malformed_provider_success_is_not_reported_as_submitted(self):
        with patch.dict(assets.os.environ, {"MESHY_API_KEY": "example-secret"}), patch.object(assets, "_http", return_value=(b'{"unexpected": true}', "application/json")):
            with self.assertRaisesRegex(ValueError, "no valid task id"):
                assets.execute(assets.build_plan(brief()))
        self.assertTrue((self.root / "scratch/external-tools/test-prop-v1/response.json").exists())

    def test_brief_size_is_bounded(self):
        path = self.root / "large.json"
        path.write_text(" " * 65537)
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            assets.load_brief(path)


if __name__ == "__main__":
    unittest.main()
