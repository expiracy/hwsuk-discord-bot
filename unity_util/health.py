import json
import time
import os
import sys
from pathlib import Path


def record(path, ready):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'ready': ready, 'updated': time.monotonic()}))
    temporary.replace(path)


def is_healthy(path, max_age=90):
    try:
        status = json.loads(Path(path).read_text())
        age = time.monotonic() - status['updated']
        return status.get('ready') is True and 0 <= age <= max_age
    except (OSError, ValueError, TypeError, KeyError):
        return False


if __name__ == '__main__':
    sys.exit(0 if is_healthy(os.environ.get('BOT_HEALTH_FILE', '/tmp/hwsuk-health.json')) else 1)
