"""Exercise an isolated deployment without using a live Discord/Reddit account."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import asyncio, importlib.util, os
from pathlib import Path
from unittest.mock import AsyncMock, patch
import motor.motor_asyncio
from pymongo.errors import OperationFailure
from unity_util import bot_config as cfg

assert os.getuid() == 10001
assert os.statvfs('/app').f_flag & os.ST_RDONLY
assert not Path('/app/.env').exists()
assert not Path('/app/tests').exists()
assert importlib.util.find_spec('coverage') is None
assert 'DISCORD_TOKEN' not in os.environ and 'MONGODB_PASSWORD' not in os.environ
assert cfg.DISCORD_TOKEN == 'docker-test-token'
try:
    Path('/app/should-not-write').write_text('unexpected')
except OSError:
    pass
else:
    raise AssertionError('The application filesystem is writable')

async def check():
    mongo = motor.motor_asyncio.AsyncIOMotorClient(host=cfg.MONGODB_HOST, port=int(cfg.MONGODB_PORT),
        username=cfg.MONGODB_USERNAME, password=cfg.MONGODB_PASSWORD, authSource=cfg.MONGODB_DATABASE,
        authMechanism='SCRAM-SHA-1', replicaSet='rs01', serverSelectionTimeoutMS=5000)
    try:
        collection = mongo[cfg.MONGODB_DATABASE].docker_probe
        if os.environ.get('EXPECT_EXISTING') == '1':
            assert (await collection.find_one({'_id':'portable'}))['value'] == 'persisted'
        else:
            await collection.update_one({'_id':'portable'}, {'$set':{'value':'persisted'}}, upsert=True)
        try:
            await mongo.admin.command({'replSetGetStatus':1})
        except OperationFailure as error:
            assert error.code == 13
        else:
            raise AssertionError('The bot database user has administrator privileges')
    finally:
        mongo.close()
    import bot
    async with bot.client:
        with patch.object(bot.client.tree, 'sync', AsyncMock(return_value=[])):
            await bot.client.setup_hook()
        assert set(bot.client.extensions) == {f'unity_cogs.{name}' for name in bot.conf['preloaded']}
    print('Runtime, secret mounts, database auth, and extension loading passed.', flush=True)
asyncio.run(check())
'''

DATABASE_TESTS = r'''
import os, unittest
from pathlib import Path
from urllib.parse import quote
password = Path('/run/db-config/admin-password').read_text().strip()
os.environ['TEST_MONGODB_URI'] = 'mongodb://hwsuk_admin:' + quote(password, safe='') + '@127.0.0.1:27017/admin?directConnection=true&replicaSet=rs01'
suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_database_integration')
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
'''

SIGNAL_TEST = r'''
import asyncio, discord
client = discord.Client(intents=discord.Intents.none())
async def start(*args, **kwargs):
    print('signal-test-ready', flush=True)
    await asyncio.Event().wait()
client.start = start
client.run('unused', log_handler=None)
print('graceful-shutdown', flush=True)
'''


def run(*args, capture=False, timeout=180, env=None):
    return subprocess.run(args, check=True, text=True, capture_output=capture, timeout=timeout, env=env)


def portable_deployment(directory, values):
    portable = Path(directory) / 'portable'
    portable.mkdir()
    for name in ('compose.yaml', 'config.json', 'deploy.sh'):
        shutil.copy(ROOT / name, portable / name)
    assert not (portable / 'bot.py').exists() and not (portable / 'docker').exists()
    project = 'hwsuk-portable-check-' + uuid.uuid4().hex[:10]
    local_values = {key:value for key,value in values.items() if not key.startswith('HWSUK_')}
    (portable / '.env').write_text('\n'.join(f"{key}='{value}'" for key,value in local_values.items()) + '\n')
    (portable / '.env').chmod(0o600)
    override = {'services': {'bot': {'entrypoint':['python', '-c', PROBE.replace('$', '$$')], 'restart':'no'}}}
    (portable / 'compose.override.yaml').write_text(json.dumps(override))
    environment = {key:value for key,value in os.environ.items() if key not in values and not key.startswith('COMPOSE_')}
    environment['COMPOSE_PROJECT_NAME'] = project
    command = ['docker', 'compose', '-f', str(portable / 'compose.yaml'), '-f', str(portable / 'compose.override.yaml'),
               '--env-file', str(portable / '.env'), '-p', project]
    try:
        print('Deploying prebuilt images without a source tree.', flush=True)
        run('sh', str(portable / 'deploy.sh'), '--no-build', env=environment)
        container = run(*command, 'ps', '-aq', 'bot', capture=True, env=environment).stdout.strip()
        code = run('docker', 'wait', container, capture=True).stdout.strip()
        run('docker', 'logs', container)
        assert code == '0'
    finally:
        run(*command, 'down', '--volumes', '--remove-orphans', env=environment)


def main():
    project = 'hwsuk-docker-check-' + uuid.uuid4().hex[:10]
    signal_container = project + '-signal'
    with tempfile.TemporaryDirectory(prefix='hwsuk-docker-') as directory:
        env = Path(directory) / '.env'
        secret_directory = Path(directory) / 'secrets'
        secret_directory.mkdir(mode=0o700)
        values = {
            'DISCORD_TOKEN':'docker-test-token', 'DISCORD_SERVER_ID':'1',
            'MONGODB_DATABASE':'docker_test', 'MONGODB_USERNAME':'docker_bot',
            'MONGODB_PASSWORD':secrets.token_hex(24) + '-@:/?[]$',
            'PRAW_CLIENT_ID':'unused', 'PRAW_CLIENT_SECRET':'unused', 'PRAW_PASSWORD':'unused',
            'PRAW_USERNAME':'tester', 'DVLA_API_KEY':'unused',
            'BOT_IMAGE':'hwsuk-discord-bot:local', 'MONGO_IMAGE':'hwsuk-mongo:local',
            'HWSUK_SECRETS_DIR':str(secret_directory),
            'HWSUK_SETUP_UID':str(os.getuid()), 'HWSUK_SETUP_GID':str(os.getgid()),
        }
        env.write_text('\n'.join(f"{key}='{value}'" for key, value in values.items()) + '\n')
        env.chmod(0o600)
        command = ['docker', 'compose', '-f', str(ROOT / 'compose.yaml'), '--env-file', str(env), '-p', project]
        environment = {key:value for key,value in os.environ.items() if key not in values and not key.startswith('COMPOSE_')}

        def compose(*args, **kwargs):
            return run(*command, *args, env=environment, **kwargs)

        def provision():
            compose('up', '--no-build', '-d', 'mongo-init')
            container = compose('ps', '-aq', 'mongo-init', capture=True).stdout.strip()
            code = run('docker', 'wait', container, capture=True).stdout.strip()
            if code != '0':
                compose('logs', '--tail', '30', 'mongo-init')
                raise AssertionError('Database bootstrap failed')

        try:
            print('Checking Compose configuration and first startup.', flush=True)
            compose('config', '--quiet')
            compose('run', '--rm', '--no-deps', 'prepare')
            provision()
            compose('run', '--rm', '--no-deps', '--entrypoint', 'python', 'bot', '-c', PROBE)

            mongo = compose('ps', '-q', 'mongo', capture=True).stdout.strip()
            details = json.loads(run('docker', 'inspect', mongo, capture=True).stdout)[0]
            assert details['Config']['User'] == 'mongodb'
            assert not details['HostConfig'].get('PortBindings')
            config_volume = next(m['Name'] for m in details['Mounts'] if m['Destination'] == '/data/configdb')

            print('Running real MongoDB integration tests.', flush=True)
            run('docker', 'run', '--rm', '--read-only', '--tmpfs', '/tmp:mode=1777', '--user', '999:999',
                '--network', 'container:' + mongo, '--mount', f'type=volume,src={config_volume},dst=/run/db-config,readonly',
                'hwsuk-discord-bot:test', 'python', '-c', DATABASE_TESTS)

            print('Recreating MongoDB and verifying persisted data and idempotent bootstrap.', flush=True)
            compose('up', '--no-build', '-d', '--no-deps', '--force-recreate', 'mongo')
            provision()
            new_mongo = compose('ps', '-q', 'mongo', capture=True).stdout.strip()
            assert new_mongo != mongo
            compose('run', '--rm', '--no-deps', '--entrypoint', 'python', '-e', 'EXPECT_EXISTING=1', 'bot', '-c', PROBE)

            print('Checking graceful SIGINT shutdown through Docker init.', flush=True)
            run('docker', 'run', '-d', '--name', signal_container, '--init', '--read-only', '--tmpfs', '/tmp:mode=1777',
                'hwsuk-discord-bot:local', 'python', '-c', SIGNAL_TEST)
            for attempt in range(30):
                if 'signal-test-ready' in run('docker', 'logs', signal_container, capture=True).stdout:
                    break
                time.sleep(0.2)
            else:
                raise AssertionError('Signal test did not start')
            run('docker', 'stop', '--timeout', '10', signal_container)
            state = json.loads(run('docker', 'inspect', signal_container, capture=True).stdout)[0]['State']
            assert state['ExitCode'] == 0
            assert 'graceful-shutdown' in run('docker', 'logs', signal_container, capture=True).stdout
            portable_deployment(directory, values)
            print('All Docker deployment checks passed. No live Discord login was attempted.', flush=True)
        finally:
            subprocess.run(['docker', 'rm', '-f', signal_container], capture_output=True)
            compose('down', '--volumes', '--remove-orphans')


if __name__ == '__main__':
    main()
