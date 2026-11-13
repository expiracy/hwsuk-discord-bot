# Testing the Discord bot

The suite covers commands, event handlers, persistence decisions, failures, and
Discord API boundaries. It exercises real Discord.py 2.7.1 command registration,
permission checks, embeds, views, and interaction responses. HTTP fixtures use the
real HTTPX client and BeautifulSoup parser. Discord delivery, Reddit, and MongoDB
are isolated in the default run.

Current default result on Python 3.11: **227 passed, 4 skipped**. The read-only
Linux/Python 3.13 test image has the same result. The four database integration
tests also passed separately against authenticated MongoDB 8 in the Docker smoke run.
Coverage is **94.91% of statements and 86.18% of branches**, with no coverage exclusions.
The combined coverage score is 93.27%; CI requires at least 90%. This is broad
regression coverage, not proof of every possible input, outage, or live permission.
Use the coverage report to inspect the remaining paths.

## Run locally

From the repository directory:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -W error::RuntimeWarning -m coverage run -m unittest discover -v
.venv/bin/python -m coverage report
```

For a quick run without measuring coverage:

```sh
.venv/bin/python -m unittest discover -v
```

The unit tests supply dummy configuration; do not source production credentials.
Warning/error messages from deliberate fault injection are expected. The unittest
summary and exit status determine whether the suite passed.

## Covered scenarios

| Area | Evidence |
|---|---|
| Extensions and startup | All configured cogs and aliases register; failures stop startup; owner operations await completion; slash commands sync; tasks stop on unload. |
| Discord access | Non-owners and users without moderator permissions are rejected; guild-only commands and typed options are registered; interactions are acknowledged before slow work. |
| Messages and components | Replayed content cannot trigger mentions; unexpected errors are private; buttons restrict access to the requester, wrap pages, and disable on timeout. |
| Verification | Only successful role assignment acknowledges queued work; closed DMs do not undo success; missing members/roles, database failures, malformed entries, concurrent processing, and retries are exercised. |
| Trade roles and lookup | String IDs resolve correctly; lookups treat regex characters literally; viewing roles does not mutate them; failed replacements preserve old roles. |
| Account administration | Ban/unban use valid atomic updates; other-server bans/unbans do not change verification; cancellation/timeouts and Discord permission failures preserve verification records. |
| Reddit | Flair updates run off the gateway event-loop thread; errors are reported as failures. |
| Feedback | Raw events work for uncached messages; bots, unrelated channels, and below-threshold votes are ignored; concurrent notifications are deduplicated per process; failed delivery can be retried; the 24-hour window and embed limits are enforced. |
| Reports | Unicode reactions, missing channels/members/messages, DMs, duplicates, atomic upserts/deletes, retraction, and cached/uncached deletion are covered. |
| Posting limiter | Complete cooldown history, early stopping, bot/whitelist exemptions, deletion errors, closed-DM fallback, positive durations, expiry, and cancellation cleanup are covered. |
| Notes | Create/view/find, pagination, hash collisions, confirmation identity, cancellation, timeout, database failures, reaction-cleanup denial, and embed length limits are covered. |
| CeX | Product URLs and case-sensitive IDs, result bounds, prices, HTTP failures, malformed JSON, and real-client response parsing are covered. |
| eBay | HTML fixtures, exclusions, sold-date parsing, prices/postage, quartiles, outliers, CAPTCHA-like pages, timeouts, connection errors, and query encoding are covered. |
| MOT | Vehicle/test fixtures, expiry dates, unknown colours, year selection, pagination, missing results, timeouts, and HTTP failures are covered. |
| USL | Disabled service returns unknown status; username validation, response rendering, and service errors are covered. |
| Configuration | Missing/empty required values, defaults, numeric parsing, and secret-free diagnostics are covered. |

## Database integration

Four additional tests use a real MongoDB replica set to check concurrent report
creation, existing report compatibility, at-most-once removal, and verification
queue persistence. They are skipped unless `TEST_MONGODB_URI` is explicitly set.
The URI must point to localhost. Each test creates a unique `hwsuk_tests_*`
database and removes that database during cleanup.

With an isolated local replica set running on port 27018:

```sh
TEST_MONGODB_URI='mongodb://127.0.0.1:27018/?replicaSet=rs01' \
  .venv/bin/python -m unittest tests.test_database_integration -v
```

The [CI workflow](.github/workflows/tests.yml) includes Docker startup and
replica-set initialisation. All four tests passed in an isolated authenticated
MongoDB 8 replica set via `python3 tests/docker_smoke.py`. Mock-based unit tests
alone do not establish that result or verify production authentication.

## CI

The workflow installs the declared dependencies and runs the suite with branch
coverage on Python 3.11, 3.12, 3.13, and 3.14. A separate job runs the four database
integration tests against MongoDB 7. The workflow uses read-only repository
permissions, disables persisted checkout credentials, and has job time limits.
Its YAML syntax was checked locally; GitHub-hosted jobs have not run in this session.

A Docker job also builds the runtime/test/database images, runs the suite in a
non-root read-only container, and invokes [the deployment smoke checks](tests/docker_smoke.py).
Those checks passed locally on arm64: real secret mounts, database-scoped user
permissions, data surviving recreation, idempotent bootstrap, graceful shutdown,
and deployment from prebuilt images without source files. The amd64 app image
was also built and its dependencies imported successfully under emulation.
See [DOCKER.md](DOCKER.md) for the image/mount design and operational commands.

## Discord guidance and remaining live checks

The checks follow Discord's guidance on [interaction acknowledgements](https://docs.discord.com/developers/interactions/receiving-and-responding),
[message limits and allowed mentions](https://docs.discord.com/developers/resources/message),
[permissions](https://docs.discord.com/developers/topics/permissions), and avoiding
[blocking the event loop](https://discordpy.readthedocs.io/en/stable/faq.html#what-does-blocking-mean).
Discord REST calls continue through Discord.py's rate-limit handling.

- [ ] Enable Server Members and Message Content intents for a dedicated test bot.
- [ ] Install with the bot and application-command scopes; check slash-command sync and button delivery in the configured server.
- [ ] Verify channel overrides, moderator permissions, and the bot's position above roles it assigns, including denied actions.
- [ ] Verify MongoDB replica-set authentication and the verification website's queue schema against a test database.
- [ ] Check current CeX/eBay/Reddit/MOT responses and credentials from the deployment host.
- [ ] Exercise restart/reconnect, reaction delivery, and permission revocation against Discord.

Feedback deduplication is process-local and resets on restart. There is no
cross-process queue claim or transactional outbox spanning MongoDB and Discord;
exactly-once delivery across crashes is not guaranteed. Run a single bot instance.
The legacy MOT endpoint and disabled USL API are not restored by offline tests.
Reddit flair updates still target `hardwareswapuk`; keep those calls mocked until
an approved test target is available. The automated suite never invokes that write.
