import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from unity_util import health


class HealthTests(unittest.TestCase):
    def test_missing_or_invalid_heartbeat_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            self.assertFalse(health.is_healthy(path))
            path.write_text("invalid")
            self.assertFalse(health.is_healthy(path))

    def test_stale_heartbeat_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            with patch.object(health.time, "monotonic", return_value=100):
                health.record(path, True)
            with patch.object(health.time, "monotonic", return_value=191):
                self.assertFalse(health.is_healthy(path))

    def test_disconnected_gateway_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            health.record(path, False)
            self.assertFalse(health.is_healthy(path))

    def test_fresh_ready_heartbeat_is_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            health.record(path, True)
            self.assertTrue(health.is_healthy(path))
