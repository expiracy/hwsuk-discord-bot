# Docker deployment

The supported deployment is one bot plus a private MongoDB replica set. You need
Docker Engine with modern Docker Compose, or Docker Desktop using Linux containers.
No host Python, MongoDB, or systemd installation is required. Use Linux amd64 or
arm64 hardware supported by the official MongoDB image; allow roughly 2 GB RAM.

## First deployment

Keep your existing `.env` if you already have one. On a fresh checkout:

```sh
test -f .env || cp .env.example .env
chmod 600 .env
```

Edit `.env`: fill in the Discord token, server/channel/role IDs, a strong
`MONGODB_PASSWORD`, and the API credentials for the integrations you use.
Edit `config.json` for the enabled cogs and your server's trade-role IDs.
For a Discord-only trial, enable just `feedback`, `limiter`, `embedremover`, and
`rendermeme`; the Reddit/MOT secrets may be nonempty `unused` placeholders.
Enable the Discord intents and installation scopes described in [README.md](README.md).

Start everything with:

```sh
sh deploy.sh
docker compose ps -a
docker compose logs -f bot
```

The script builds both images, prepares runtime secret files, starts MongoDB,
initialises `rs01`, creates a database-scoped application user, and then starts
the bot. An administrator password and replica key are generated automatically.
The bot never receives the administrator credentials. `prepare` and `mongo-init`
are one-shot jobs, so a successful exit is normal for those containers.

Do not run bare `docker compose up` on a fresh checkout: `deploy.sh` first creates
the protected secret files that the read-only services need.

## What belongs in an image or a mount?

| Item | Production treatment | Reason |
|---|---|---|
| Application code and Python dependencies | Baked into the bot image | The same tested application runs on every host; code changes require a rebuild. |
| `config.json` | Single read-only bind mount | Server IDs, role mappings, and enabled cogs can change without rebuilding dependencies. Restart the bot after editing. |
| Tokens/passwords | Read-only Compose secret files | Credentials stay outside the image and runtime container environment. |
| MongoDB data | `mongo_data` named volume | Recreating or updating a container preserves application records. |
| Replica key and administrator password | `mongo_config` named volume | Database authentication survives container recreation. Keep this volume with the database. |
| Logs | stdout/stderr, bounded Docker local logging | No host log directory or permission setup is needed. |
| Health files and temporary work | In-memory `/tmp` | Disposable state does not belong in a database backup. |

The bot runs as UID 10001 and MongoDB as its `mongodb` user. Both runtime
filesystems are read-only, capabilities are dropped, and privilege escalation is
disabled. MongoDB is on an internal network, has authentication enabled, and has
no host port published. The bot additionally has an outbound network for Discord
and upstream APIs. There is no web port to open on the host.

The `.dockerignore` files allow only required build inputs. `.env`, prepared
secrets, Git history, local virtual environments, and backups are excluded.
The separate `test` stage contains tests and development dependencies; production
contains neither.

## Secrets and updates

`.env` is the local source for credentials, not a build input. The one-shot
`prepare` job receives environment-backed Compose secrets and writes individual
files into `.docker-secrets`. The host directory is mode 0700; its files are
0444 so the fixed container users can read their explicitly granted mounts.
Do not relax the directory permissions. These are local file mounts, not an
encrypted secret vault; protect `.env`, `.docker-secrets`, and backups.

The preparation container has no network and no persistent writable filesystem
apart from that directory. It is deliberately not read-only because Compose
cannot inject environment-backed secrets into a read-only service. The bot and
database use file-backed secrets and remain read-only.

Blank secrets and `REPLACE_...` template values are rejected before database
provisioning. Preparation defaults to your host UID/GID; `HWSUK_SETUP_UID` and
`HWSUK_SETUP_GID` can override these for rootless or user-namespace-remapped Docker
bind mounts. Those mappings need host-specific validation; runtime users stay fixed.

After a code, configuration, or API-token change, run:

```sh
sh deploy.sh
```

This refreshes base images, rebuilds changed layers, regenerates secrets, and
recreates the bot and bootstrap job. An unchanged database image/container does
not need to be replaced. Base tags fix the Python minor version/distribution and
MongoDB major/minor series; `--pull` obtains their current patch images. Keep
tested image artifacts or use registry digests when an immutable release is needed.

Changing `MONGODB_PASSWORD` in `.env` alone does not rotate an existing database
user's password. Coordinate that change in MongoDB and with other clients first;
bootstrap intentionally refuses mismatched stored credentials instead of silently
changing them. Changing the database name creates a different database, not a migration.

## Monitoring and stopping

```sh
docker compose ps -a
docker compose logs --tail 100 bot mongo-init
docker compose restart bot
docker compose stop
docker compose down
```

`down` keeps named volumes. **`down --volumes` deletes the database and its
authentication state**; use it only for an intentional reset of disposable data.
Run one bot instance for this server; in-memory notification deduplication and
queue locking are not a distributed coordination system.

The bot health check requires a fresh event-loop heartbeat and a connected
Discord gateway. MongoDB has its own authenticated health check. Docker's
`unless-stopped` policy restarts exited containers and starts them after a host
restart; it does not restart a process solely because a health check is unhealthy.
Discord.py handles ordinary gateway reconnects. Inspect logs when a service stays
unhealthy; gateway health does not establish that every upstream API is working.

`SIGINT`, exec-form commands, Docker's init process, and a shutdown grace period
allow Discord.py and MongoDB to close cleanly. Logs rotate at 10 MB with three
files per service. Native Python runs retain optional file logging; Docker disables it.

## Moving to another machine

The easiest route is to copy/clone the project, copy `.env` securely, install
Docker, and run `sh deploy.sh`. Back up and restore the application database when
moving existing records. Docker named volumes are local to a host; they do not
follow an image or Git checkout automatically.

To deploy without application source or rebuilding, first export the native images:

```sh
docker image save -o hwsuk-images.tar hwsuk-discord-bot:local hwsuk-mongo:local
```

Transfer the archive plus `compose.yaml`, `config.json`, `deploy.sh`, and `.env`.
On the target machine, in that deployment directory:

```sh
docker image load -i hwsuk-images.tar
sh deploy.sh --no-build
```

No source directory or Dockerfiles are needed in this mode. An archive retains
its CPU architecture: rebuild on a different architecture or distribute
multi-platform images through your registry. `BOT_IMAGE` and `MONGO_IMAGE` can
select already-loaded registry/version tags; no image is published automatically.

## Backup and restore

Pause the bot and other database writers, including the verification website,
for a consistent application backup. The following dumps only the application
database, so a restore does not overwrite a new host's administrator credentials:

```sh
docker compose stop bot
mkdir -p backups
umask 077
docker compose exec -T mongo sh -c 'exec mongodump --host 127.0.0.1 --username "$MONGO_INITDB_ROOT_USERNAME" --password "$(cat "$MONGO_INITDB_ROOT_PASSWORD_FILE")" --authenticationDatabase admin --db "$MONGODB_DATABASE" --archive --gzip' > backups/bot.archive.gz
docker compose start bot
```

On a freshly initialised target with the same `MONGODB_DATABASE`, stop the bot and restore:

```sh
docker compose stop bot
docker compose exec -T mongo sh -c 'exec mongorestore --host 127.0.0.1 --username "$MONGO_INITDB_ROOT_USERNAME" --password "$(cat "$MONGO_INITDB_ROOT_PASSWORD_FILE")" --authenticationDatabase admin --archive --gzip' < backups/bot.archive.gz
docker compose start bot
```

Restore into a fresh database. Restoring over existing records needs an explicit
merge/reset decision; the commands above do not drop existing collections.
Keep backups off the host and practise restoring them. The external verification
website must be pointed at the same database; hosting the bot does not move that site.

## Development and checks

Production deliberately does not mount source. For local iteration after normal
setup, the optional development override mounts only source files/directories read-only:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --no-build bot
```

Use `/reload` for changed cogs or restart for startup code; dependency changes
still require rebuilding. Run `sh deploy.sh` to return to the production layout.

Container checks:

```sh
docker build --target test -t hwsuk-discord-bot:test .
docker run --rm --read-only --tmpfs /tmp:mode=1777 hwsuk-discord-bot:test
python3 tests/docker_smoke.py
```

The smoke script needs host Python only as a test driver. It creates uniquely
named disposable stacks and checks runtime hardening, secret mounts, real database
authentication/permissions, all four database integration tests, persistence after
recreation, idempotent bootstrap, graceful shutdown, and source-free deployment.
It cleans up only its test stacks. No live Discord login or Reddit flair write is attempted.
The GitHub workflow runs these checks on changes. Live Discord permissions and
external APIs still need the checks in [TESTING.md](TESTING.md).

The deployment follows Docker's [build guidance](https://docs.docker.com/build/building/best-practices/),
[secret handling](https://docs.docker.com/compose/how-tos/use-secrets/), and
[dependency readiness](https://docs.docker.com/compose/how-tos/startup-order/) guidance.
