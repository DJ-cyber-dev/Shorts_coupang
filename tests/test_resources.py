import unittest
import os
import subprocess
from unittest.mock import patch

from shorts_studio.text_removal.resources import ResourceSettings


class ResourceSettingsTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows process priority only")
    def test_windows_worker_priority_can_be_lowered(self):
        from shorts_studio.core.engine import flags
        self.assertEqual(flags(low_priority=True)["creationflags"],
                         subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)

    def test_rejects_unsupported_cpu_cap_and_non_boolean_priority(self):
        for settings in (ResourceSettings(cpu_threads=0),
                         ResourceSettings(background_priority="yes")):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                settings.validate()

    def test_thread_cap_is_bounded_by_available_logical_processors(self):
        with patch("shorts_studio.text_removal.resources.available_cpu_threads", return_value=4):
            ResourceSettings(cpu_threads=4).validate()
            with self.assertRaisesRegex(ValueError, "1~4"):
                ResourceSettings(cpu_threads=5).validate()

if __name__ == "__main__":
    unittest.main()
