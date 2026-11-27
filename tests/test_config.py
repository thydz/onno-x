"""Regression tests for config loading and saving.

A corrupt config.json used to be silently replaced by DEFAULT_MODELS in memory,
so the next save_config wrote defaults over the user's file -- API keys gone with
no message. Loading must now quarantine the bad file and say so.
"""

import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from onno_x import config as config_mod
from onno_x.config import DEFAULT_MODELS, Config, ModelSpec, load_config, save_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(config_mod, "CONFIG_DIR", self.root),
            mock.patch.object(config_mod, "CONFIG_FILE", self.root / "config.json"),
        ]
        for p in self._patches:
            p.start()
        self.cfg_file = self.root / "config.json"

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def test_save_writes_private_file_atomically(self):
        cfg = Config(
            active_model="mine",
            models={"mine": ModelSpec(name="mine", provider="openai", model_id="m", api_key="sk-secret")},
        )
        save_config(cfg)

        self.assertTrue(self.cfg_file.exists())
        mode = stat.S_IMODE(self.cfg_file.stat().st_mode)
        self.assertEqual(mode & 0o077, 0, f"config too permissive: {oct(mode)}")
        self.assertEqual(load_config().models["mine"].api_key, "sk-secret")
        leftovers = [p for p in self.root.iterdir() if p.name.startswith(".config-")]
        self.assertEqual(leftovers, [], "temp file left behind after atomic save")

    def test_corrupt_config_is_quarantined_not_overwritten(self):
        self.cfg_file.write_text("{not json at all", encoding="utf-8")

        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            cfg = load_config()

        self.assertIn("Config tidak bisa dibaca", stderr.getvalue())
        self.assertIn("corrupt-", stderr.getvalue())
        self.assertEqual(set(cfg.models), set(DEFAULT_MODELS))

        backups = list(self.root.glob("config.json.corrupt-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{not json at all")
        # The original path is free again, so a later save cannot clobber the backup.
        self.assertFalse(self.cfg_file.exists())

    def test_config_object_is_still_valid_after_quarantine(self):
        self.cfg_file.write_text(json.dumps({"active_model": "x", "models": "nope"}), encoding="utf-8")
        with mock.patch("sys.stderr", io.StringIO()):
            cfg = load_config()
        self.assertEqual(set(cfg.models), set(DEFAULT_MODELS))
        if cfg.models:
            self.assertIn(cfg.active_model, cfg.models)

    def test_missing_models_falls_back_to_defaults(self):
        self.cfg_file.write_text(json.dumps({"active_model": "ghost", "models": {}}), encoding="utf-8")
        cfg = load_config()
        self.assertEqual(set(cfg.models), set(DEFAULT_MODELS))
        if cfg.models:
            self.assertIn(cfg.active_model, cfg.models)

    def test_dangling_active_model_is_repaired(self):
        payload = {
            "active_model": "deleted-model",
            "models": {"kept": {"name": "kept", "provider": "openai", "model_id": "m"}},
        }
        self.cfg_file.write_text(json.dumps(payload), encoding="utf-8")
        cfg = load_config()
        self.assertEqual(cfg.active_model, "kept")
        self.assertEqual(list(cfg.models), ["kept"])

    def test_first_run_creates_default_config(self):
        cfg = load_config()
        self.assertTrue(self.cfg_file.exists())
        self.assertEqual(set(cfg.models), set(DEFAULT_MODELS))


if __name__ == "__main__":
    unittest.main()
