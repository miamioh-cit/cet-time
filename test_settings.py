import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from deploy.settings import load_settings, settings
from deploy.render import render


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            'IMAGE_REPOSITORY': 'docker.io/example/cet-time',
            'PUBLIC_URL': 'https://time.example.edu',
            'TLS_SECRET_NAME': 'cet-time-tls',
            'INGRESS_CLASS': 'nginx',
        }

    def test_settings_render_and_bind_credentials(self):
        config = settings(self.values)
        self.assertEqual(config['REGISTRY_CREDENTIAL_ID'], 'docker-registry')
        self.assertEqual(config['KUBECONFIG_CREDENTIAL_ID'], 'cet-time')
        objects = render({**config, 'IMAGE_REF': config['IMAGE_REPOSITORY'] + ':build-1'})['items']
        ingress = next(item for item in objects if item['kind'] == 'Ingress')
        self.assertEqual(ingress['spec']['ingressClassName'], 'nginx')
        self.assertEqual(ingress['spec']['tls'][0]['secretName'], 'cet-time-tls')

    def test_false_ingress_does_not_require_tls(self):
        self.values.update(ENABLE_INGRESS=False, TLS_SECRET_NAME='')
        config = settings(self.values)
        self.assertEqual(config['ENABLE_INGRESS'], 'false')
        objects = render({**config, 'IMAGE_REF': config['IMAGE_REPOSITORY'] + ':build-1'})['items']
        self.assertNotIn('Ingress', [item['kind'] for item in objects])

    def test_reports_all_missing_setup_values(self):
        with self.assertRaisesRegex(ValueError, 'IMAGE_REPOSITORY, PUBLIC_URL, TLS_SECRET_NAME'):
            settings({})

    def test_rejects_secret_and_unknown_keys_without_echoing_values(self):
        for key in ('TRELLO_TOKEN', 'ADMIN_PASSWORD', 'PATH', 'PUBLIC_URl'):
            with self.subTest(key=key):
                with self.assertRaises(ValueError) as exc:
                    settings({**self.values, key: 'do-not-log-this'})
                self.assertNotIn('do-not-log-this', str(exc.exception))

    def test_rejects_wrong_types_and_environment_line_injection(self):
        for key, value in [('ENABLE_INGRESS', 'false'), ('ENABLE_INGRESS', 0),
                           ('STORAGE_SIZE', 5), ('KUBE_NAMESPACE', None),
                           ('REGISTRY_CREDENTIAL_ID', 'registry\nPATH=bad'),
                           ('REGISTRY_CREDENTIAL_ID', 'registry\x00bad')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                settings({**self.values, key: value})
        with self.assertRaises(ValueError):
            settings([])

    def test_reuses_existing_manifest_validation(self):
        for key, value in [('PUBLIC_URL', 'http://time.example.edu'),
                           ('STORAGE_SIZE', '0Gi'), ('IMAGE_REPOSITORY', 'example/cet-time')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                settings({**self.values, key: value})

    def test_cli_ignores_stale_jenkins_environment_and_outputs_literal_values(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            self.values.update(ENABLE_INGRESS=False, TLS_SECRET_NAME='', IMAGE_PULL_SECRET='')
            path.write_text(json.dumps(self.values), encoding='utf-8')
            result = subprocess.run(
                [sys.executable, 'deploy/settings.py', '--config', str(path)],
                env={**os.environ, 'PUBLIC_URL': 'https://stale.example.edu', 'ENABLE_INGRESS': 'true'},
                capture_output=True, text=True, check=True,
            )
        config = dict(line.split('=', 1) for line in result.stdout.splitlines())
        self.assertEqual(config, settings(self.values))
        self.assertEqual(config['PUBLIC_URL'], 'https://time.example.edu')
        self.assertEqual(config['ENABLE_INGRESS'], 'false')
        self.assertEqual(config['IMAGE_PULL_SECRET'], '')

    def test_bad_files_emit_no_partial_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            for raw in ('{bad-json', '{"ENABLE_INGRESS":true,"ENABLE_INGRESS":false}', '[]'):
                path.write_text(raw, encoding='utf-8')
                result = subprocess.run([sys.executable, 'deploy/settings.py', '--config', str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')
            with self.assertRaisesRegex(ValueError, 'Cannot read'):
                load_settings(Path(folder) / 'missing.json')


if __name__ == '__main__':
    unittest.main()
