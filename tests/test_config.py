import contextlib
import importlib
import io
import os
import runpy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.support import TEST_ENV


class ConfigurationTests(unittest.TestCase):
    def test_empty_required_secret_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text("\n")
            with patch.dict(os.environ, {"TOKEN_FILE":str(path)}, clear=True):
                with self.assertRaisesRegex(RuntimeError,"missing or empty"):
                    self.config.get_env("TOKEN", required=True)

    def test_unreadable_secret_reports_key_without_secret_contents(self):
        with patch.dict(os.environ, {"TOKEN_FILE":"/no-such-secret"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "secret file for TOKEN"):
                self.config.get_env("TOKEN", required=True)

    def test_environment_and_file_secret_are_mutually_exclusive(self):
        with patch.dict(os.environ, {"TOKEN":"private", "TOKEN_FILE":"/ignored"}, clear=True):
            with self.assertRaisesRegex(RuntimeError,"only one"):
                self.config.get_env("TOKEN", required=True)

    def test_required_secret_can_be_loaded_from_a_mounted_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token"
            path.write_text("mounted-secret\n")
            with patch.dict(os.environ, {"TOKEN_FILE":str(path)}, clear=True):
                self.assertEqual(self.config.get_env("TOKEN", required=True), "mounted-secret")

    def test_required_default_warning_does_not_print_secret_values(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"REQUIRED":"private-value"}, clear=True), contextlib.redirect_stdout(output):
            self.assertEqual(self.config.get_env("REQUIRED", required=True, or_else="private-default"), "private-value")
        self.assertIn("REQUIRED", output.getvalue())
        self.assertNotIn("private-value", output.getvalue())
        self.assertNotIn("private-default", output.getvalue())

    def test_non_numeric_channel_id_fails_configuration_loading(self):
        with patch.dict(os.environ, {**TEST_ENV, "REACTION_CHANNEL_ID":"invalid"}, clear=True):
            with self.assertRaises(ValueError):
                runpy.run_path("unity_util/bot_config.py")

    def test_empty_required_credential_is_rejected(self):
        with patch.dict(os.environ, {"DISCORD_TOKEN":""}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DISCORD_TOKEN"):
                self.config.get_env("DISCORD_TOKEN", required=True)

    def test_required_values_do_not_silently_use_a_default(self):
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                self.config.get_env("REQUIRED", required=True, or_else="default")

    def test_explicit_environment_value_overrides_the_default(self):
        with patch.dict(os.environ, {"OPTIONAL":"chosen"}, clear=True):
            self.assertEqual(self.config.get_env("OPTIONAL", or_else="default"), "chosen")

    def test_optional_value_uses_the_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.config.get_env("OPTIONAL", or_else="default"), "default")

    def setUp(self):
        self.enterContext(patch.dict(os.environ, TEST_ENV))
        self.config = importlib.import_module("unity_util.bot_config")

    def test_required_missing_value_names_the_key_without_exposing_values(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Required environment variable MISSING is missing"):
                self.config.get_env("MISSING", required=True)
