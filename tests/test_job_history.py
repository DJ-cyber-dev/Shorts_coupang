import unittest
import os
from pathlib import Path
import tempfile
import time

from shorts_studio.jobs.history import JobHistory


class JobHistoryTests(unittest.TestCase):
    def test_persists_updates_and_marks_abandoned_work_interrupted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            history = JobHistory(root / "history")
            stale = root / ".shorts-crashed"
            stale.mkdir()
            (stale / ".shorts-studio-temp").touch()
            old_time = time.time() - 13 * 60 * 60
            os.utime(stale, (old_time, old_time))
            job = history.create(kind="video", source="https://www.youtube.com/watch?v=abc123&token=secret",
                                 output=str(root / "output.mp4"))
            self.assertEqual(job["source"], "https://www.youtube.com/watch?v=abc123")
            history.update(job["id"], stage="text removal", progress=.4)
            self.assertEqual(history.reconcile_running(), 1)
            row = history.list_recent()[0]
            self.assertEqual(row["status"], "interrupted")
            self.assertEqual(row["stage"], "app_closed")
            self.assertEqual(row["progress"], .4)
            self.assertFalse(stale.exists())

    def test_prunes_old_records_and_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as folder:
            history = JobHistory(Path(folder), max_records=2)
            first = history.create(kind="video", source="input.mp4")
            second = history.create(kind="video", source="input2.mp4")
            history.update(first["id"], stage="newer")
            history.create(kind="video", source="input3.mp4")
            self.assertEqual(len(history.list_recent()), 2)
            with self.assertRaises(ValueError):
                history.update(first["id"], progress=2)
            with self.assertRaises(ValueError):
                history.update("../escape", status="completed")


if __name__ == "__main__":
    unittest.main()
