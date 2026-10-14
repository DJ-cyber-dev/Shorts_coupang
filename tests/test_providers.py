import os
from pathlib import Path
import unittest

from shorts_studio.providers.settings import ProviderSettings


class ProviderSettingsTests(unittest.TestCase):
    def test_save_load_never_persists_secret(self):
        path = Path(__file__).with_name(f".provider-test-{os.getpid()}.toml")
        try:
            settings = ProviderSettings("openai-compatible", "vision-model", "https://api.example/v1")
            settings.save(path)
            self.assertEqual(ProviderSettings.load(path), settings)
            self.assertNotIn("api_key", path.read_text(encoding="utf-8"))
        finally:
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)

    def test_rejects_remote_http_and_embedded_credentials(self):
        with self.assertRaises(ValueError):
            ProviderSettings("custom", "model", "http://api.example/v1").validate()
        with self.assertRaises(ValueError):
            ProviderSettings("custom", "model", "https://user:pass@api.example/v1").validate()

    def test_allows_local_http_provider(self):
        ProviderSettings("local", "model", "http://127.0.0.1:1234/v1").validate()

    @unittest.skipIf(os.name == "nt", "Credential Manager is Windows-only")
    def test_non_windows_secret_storage_requires_environment(self):
        with self.assertRaisesRegex(RuntimeError, "환경 변수"):
            ProviderSettings().store_secret("secret")


if __name__ == "__main__":
    unittest.main()
