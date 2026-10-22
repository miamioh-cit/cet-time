"""Load non-secret deployment settings for Jenkins without sourcing shell code."""
import argparse
import json
from pathlib import Path

try:
    from .render import render
except ImportError:  # Invoked as python3 deploy/settings.py.
    from render import render

DEFAULTS = {
    'IMAGE_REPOSITORY': '',
    'REGISTRY_HOST': 'docker.io',
    'REGISTRY_CREDENTIAL_ID': 'docker-registry',
    'KUBECONFIG_CREDENTIAL_ID': 'cet-time',
    'KUBE_NAMESPACE': 'cet-time',
    'PUBLIC_URL': '',
    'ENABLE_INGRESS': True,
    'INGRESS_CLASS': '',
    'TLS_SECRET_NAME': '',
    'STORAGE_CLASS': '',
    'STORAGE_SIZE': '5Gi',
    'IMAGE_PULL_SECRET': '',
}
DEFAULT_PATH = Path(__file__).resolve().with_name('jenkins.json')


def settings(values):
    if not isinstance(values, dict):
        raise ValueError('Deployment settings must be a JSON object.')
    if set(values) - set(DEFAULTS):
        raise ValueError('Deployment settings contain unsupported keys; use only the documented non-secret settings.')
    result = {}
    for key, default in DEFAULTS.items():
        value = values.get(key, default)
        if key == 'ENABLE_INGRESS':
            if not isinstance(value, bool):
                raise ValueError('ENABLE_INGRESS must be a JSON boolean (true or false).')
            result[key] = str(value).lower()
        else:
            if not isinstance(value, str) or any(c in value for c in ('\r', '\n', '\x00')):
                raise ValueError(key + ' must be a single-line string.')
            result[key] = value.strip()
    required = ['IMAGE_REPOSITORY', 'PUBLIC_URL', 'REGISTRY_CREDENTIAL_ID',
                'KUBECONFIG_CREDENTIAL_ID']
    if result['ENABLE_INGRESS'] == 'true':
        required.append('TLS_SECRET_NAME')
    missing = [key for key in required if not result[key]]
    if missing:
        raise ValueError('Complete deploy/jenkins.json before building. Missing settings: ' + ', '.join(missing))
    # Reuse manifest validation before building or logging in to the registry.
    render({**result, 'IMAGE_REF': result['IMAGE_REPOSITORY'] + ':config-check'})
    return result


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Deployment settings contain duplicate JSON keys.')
        result[key] = value
    return result


def load_settings(path=DEFAULT_PATH):
    try:
        values = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Cannot read deployment settings: provide a valid UTF-8 JSON file.') from exc
    return settings(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    try:
        config = load_settings(args.config)
    except ValueError as exc:
        parser.exit(2, str(exc) + '\n')
    # Jenkins passes these as literal withEnv entries, never shell commands.
    print('\n'.join(key + '=' + value for key, value in config.items()))


if __name__ == '__main__':
    main()
