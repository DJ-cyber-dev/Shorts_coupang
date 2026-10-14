import importlib.util
from pathlib import Path
import unittest


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "Optional Streamlit dependency not installed")
class WebSmokeTest(unittest.TestCase):
    def test_initial_screen(self):
        from streamlit.testing.v1 import AppTest
        path = Path(__file__).resolve().parents[1] / "src/shorts_studio/ui/web.py"
        app = AppTest.from_file(str(path)).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Shorts Studio")
        self.assertTrue(app.button[0].disabled)
        self.assertFalse(app.checkbox)
        app.selectbox[0].set_value("crop").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].value, "crop")
        app.text_input[0].set_value("https://www.youtube.com/shorts/BaW_jenozKc").run()
        self.assertFalse(app.button[0].disabled)
        app.radio[0].set_value("파일 업로드").run()
        self.assertTrue(app.button[0].disabled)
