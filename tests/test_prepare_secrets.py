import tempfile
import unittest
from pathlib import Path

from unity_util import prepare_secrets


class PrepareSecretTests(unittest.TestCase):
    def test_template_placeholders_are_rejected_before_creating_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            source.mkdir()
            for name in prepare_secrets.NAMES:
                (source / f'input_{name}').write_text('valid-value')
            (source / 'input_discord_token').write_text('REPLACE_WITH_BOT_TOKEN')
            with self.assertRaisesRegex(ValueError, 'discord_token'):
                prepare_secrets.prepare(source, target)
            self.assertFalse((target / 'discord_token').exists())

    def test_a_read_only_temporary_file_from_an_interrupted_run_does_not_block_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            source.mkdir()
            target.mkdir()
            for name in prepare_secrets.NAMES:
                (source / f'input_{name}').write_text('new-value')
            abandoned = target / '.discord_token.tmp'
            abandoned.write_text('old-value')
            abandoned.chmod(0o444)
            prepare_secrets.prepare(source, target)
            self.assertEqual((target / 'discord_token').read_text(), 'new-value')

    def test_empty_secret_does_not_replace_existing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            source.mkdir()
            for name in prepare_secrets.NAMES:
                (source / f'input_{name}').write_text('existing-value')
            prepare_secrets.prepare(source, target)
            (source / 'input_discord_token').write_text('')
            with self.assertRaises(ValueError):
                prepare_secrets.prepare(source, target)
            self.assertEqual((target / 'discord_token').read_text(), 'existing-value')

    def test_repeated_preparation_updates_existing_read_only_secret_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            source.mkdir()
            for name in prepare_secrets.NAMES:
                (source / f'input_{name}').write_text('first-value')
            prepare_secrets.prepare(source, target)
            (source / 'input_discord_token').write_text('second-value')
            prepare_secrets.prepare(source, target)
            self.assertEqual((target / 'discord_token').read_text(), 'second-value')

    def test_secrets_are_materialised_in_a_private_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            source.mkdir()
            for name in prepare_secrets.NAMES:
                (source / f'input_{name}').write_text('secret-value')
            prepare_secrets.prepare(source, target)
            self.assertEqual((target / 'discord_token').read_text(), 'secret-value')
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertEqual((target / 'discord_token').stat().st_mode & 0o777, 0o444)
