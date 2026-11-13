from pathlib import Path
import tempfile


NAMES = ('discord_token', 'mongodb_password', 'praw_client_id', 'praw_client_secret', 'praw_password', 'dvla_api_key')


def prepare(source, target):
    source, target = Path(source), Path(target)
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.chmod(0o700)
    values = {name: (source / f'input_{name}').read_bytes() for name in NAMES}
    invalid = [name for name, value in values.items() if not value.strip() or value.strip().startswith(b'REPLACE_')]
    if invalid:
        raise ValueError('Fill in these runtime secrets before deployment: ' + ', '.join(invalid))
    for name, value in values.items():
        with tempfile.NamedTemporaryFile(dir=target, prefix=f'.{name}.', delete=False) as output:
            temporary = Path(output.name)
            output.write(value)
        try:
            temporary.chmod(0o444)
            temporary.replace(target / name)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    prepare(Path('/run/secrets'), Path('/run/hwsuk-secrets'))
