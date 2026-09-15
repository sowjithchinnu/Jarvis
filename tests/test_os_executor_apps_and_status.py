import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from os_executor import OSExecutor


class OSExecutorAppsAndStatusTests(unittest.TestCase):
    def setUp(self):
        self.executor = OSExecutor()

    def test_open_application_uses_fixed_whitelisted_command(self):
        with patch("os_executor.platform.system", return_value="Linux"), patch(
            "os_executor.subprocess.Popen"
        ) as popen:
            result = self.executor.open_application("calculator")

        self.assertEqual(result, "Application 'calculator' launched.")
        popen.assert_called_once_with(["gnome-calculator"], shell=False)

    def test_open_application_rejects_non_whitelisted_name(self):
        with patch("os_executor.subprocess.Popen") as popen:
            result = self.executor.open_application("arbitrary-command")

        self.assertIn("not allowed", result)
        self.assertIn("Allowed applications:", result)
        popen.assert_not_called()

    def test_get_battery_status_reports_present_battery(self):
        psutil = Mock()
        psutil.sensors_battery.return_value = SimpleNamespace(
            percent=82.5,
            power_plugged=True,
        )

        with patch("os_executor.psutil", psutil):
            result = self.executor.get_battery_status()

        self.assertEqual(result, "Battery: 82.5% (charging).")
        psutil.sensors_battery.assert_called_once_with()

    def test_get_battery_status_reports_no_battery(self):
        psutil = Mock()
        psutil.sensors_battery.return_value = None

        with patch("os_executor.psutil", psutil):
            result = self.executor.get_battery_status()

        self.assertEqual(result, "No battery detected.")

    def test_get_system_status_reports_cpu_memory_and_disk(self):
        psutil = Mock()
        psutil.cpu_percent.return_value = 12.3
        psutil.virtual_memory.return_value = SimpleNamespace(percent=44.4)
        psutil.disk_usage.return_value = SimpleNamespace(free=10 * 1024**3)

        with patch("os_executor.psutil", psutil):
            result = self.executor.get_system_status()

        self.assertIn("CPU: 12.3%", result)
        self.assertIn("Memory: 44.4%", result)
        self.assertIn("Available disk: 10.0 GB", result)
        psutil.cpu_percent.assert_called_once_with(interval=0.1)
        psutil.virtual_memory.assert_called_once_with()
        psutil.disk_usage.assert_called_once()

    def test_brightness_range_validation_does_not_call_library(self):
        brightness_control = Mock()

        with patch("os_executor.screen_brightness_control", brightness_control):
            below_range = self.executor.set_brightness(-1)
            above_range = self.executor.set_brightness(101)

        self.assertIn("between 0 and 100", below_range)
        self.assertIn("between 0 and 100", above_range)
        brightness_control.set_brightness.assert_not_called()

    def test_brightness_library_is_used_for_supported_display(self):
        brightness_control = Mock()
        brightness_control.get_brightness.return_value = [55]
        brightness_control.set_brightness.return_value = [70]

        with patch("os_executor.screen_brightness_control", brightness_control):
            get_result = self.executor.get_brightness()
            set_result = self.executor.set_brightness(70)

        self.assertEqual(get_result, 55)
        self.assertEqual(set_result, "Screen brightness set to 70.")
        brightness_control.get_brightness.assert_called_once_with()
        brightness_control.set_brightness.assert_called_once_with(70)

    def test_brightness_reports_unsupported_display(self):
        brightness_control = Mock()
        brightness_control.get_brightness.return_value = []

        with patch("os_executor.screen_brightness_control", brightness_control):
            result = self.executor.get_brightness()

        self.assertIn("not supported on this display/OS", result)


if __name__ == "__main__":
    unittest.main()
