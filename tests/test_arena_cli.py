import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import arena


class ArenaCommandTests(unittest.TestCase):
    def test_env_parser_preserves_literal_values_and_runtime_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('# comment\nLLM_API_KEY="synthetic $value # literal"\nTEAM_ID=63\n')
            values = arena.read_environment(path, {'TEAM_ID': '7'})
        self.assertEqual(values['TEAM_ID'], '7')
        self.assertEqual(values['LLM_API_KEY'], 'synthetic $value # literal')

    def test_day2_build_has_no_model_secret_or_selector(self):
        args = arena.build_args('local:test', 'day2')
        self.assertNotIn('--secret', args)
        self.assertNotIn('--build-arg', args)
        self.assertIn('linux/amd64', args)
        self.assertIn('--provenance=false', args)

    def test_day1_secret_path_does_not_put_values_in_command(self):
        args = arena.build_args('local:test', 'day1', '/tmp/model.env')
        self.assertIn('id=day1_llm,src=/tmp/model.env', args)
        self.assertIn('INCLUDE_DAY1_LLM=1', args)
        self.assertIn('--no-cache', args)

    def test_practice_limits_and_credentials_are_passed_by_name(self):
        values = {key: 'synthetic-secret' for key in arena.RUNTIME_KEYS}
        values['UNRELATED_SECRET'] = 'unrelated'
        args = arena.practice_args('local:test', 94, Path('/tmp/work'), values)
        self.assertNotIn('synthetic-secret', ' '.join(args))
        self.assertNotIn('UNRELATED_SECRET', args)
        for expected in ('ONLY_IDS=94', '--read-only', '2g', '256', 'ALL',
                         'no-new-privileges', 'CTF_TOKEN', 'LLM_API_KEY'):
            self.assertIn(expected, args)

    def test_missing_model_key_fails_before_docker(self):
        with self.assertRaisesRegex(ValueError, 'LLM_API_KEY'):
            arena.practice_args('local:test', 94, Path('/tmp/work'), {
                'CTF_BASE': 'https://example.test', 'CTF_TOKEN': 'synthetic',
                'LLM_BASE_URL': 'https://model.test', 'LLM_MODEL': 'test',
            })

    def test_init_preserves_existing_private_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env').write_text('CTF_TOKEN=synthetic-existing\n')
            with patch.object(arena, 'ROOT', root):
                arena.main(['init'])
            self.assertEqual((root / '.env').read_text(), 'CTF_TOKEN=synthetic-existing\n')

    def test_day2_push_stops_when_image_contains_legacy_secret(self):
        import subprocess
        with patch.object(arena, 'read_environment', return_value={'TEAM_ID': '63'}), \
             patch.object(arena, 'run', side_effect=subprocess.CalledProcessError(1, 'docker')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                arena.main(['push', '--phase', 'day2'])
        self.assertEqual(run.call_count, 1)
        self.assertNotIn('push', run.call_args.args[0])

    def test_registry_target_rejects_invalid_team(self):
        with self.assertRaises(ValueError):
            arena.image_name({'TEAM_ID': '63/other'})
