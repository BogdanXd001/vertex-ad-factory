import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from vertex_ad_factory.services.runtime_config import RuntimeConfigStore


class RuntimeConfigTests(TestCase):
    def test_secret_is_private_and_never_returned_publicly(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.json"
            store = RuntimeConfigStore(path)

            config = store.update_voiceover("top-secret", "voice-id")

            self.assertTrue(config.voiceover_ready)
            self.assertNotIn("api_key", config.public_dict())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_omitted_api_key_preserves_the_existing_secret(self) -> None:
        with TemporaryDirectory() as directory:
            store = RuntimeConfigStore(Path(directory) / "runtime.json")
            store.update_voiceover("top-secret", "voice-one")

            updated = store.update_voiceover(None, "voice-two")

            self.assertEqual(updated.elevenlabs_api_key, "top-secret")
            self.assertEqual(updated.elevenlabs_voice_id, "voice-two")
