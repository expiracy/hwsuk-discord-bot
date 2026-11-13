# HWSUK Discord Bot

## Docker deployment (recommended)

With Docker and modern Docker Compose installed, fill in `.env` and the server's
role/cog settings in `config.json`, then run `sh deploy.sh`. The script builds the
images, prepares secret mounts, initialises an authenticated MongoDB replica set,
and starts the bot. No host Python, MongoDB, or systemd installation is needed.
Keep an existing `.env`; use `.env.example` as the template for a fresh checkout.

Application code/dependencies stay in the image; `config.json` and secrets are
read-only mounts; MongoDB state lives in named volumes; logs go to Docker.
See [DOCKER.md](DOCKER.md) for setup, image transfer, updates, backups, and tests.

## Native Python deployment requirements

- Python >= 3.11
- discord.py 2.x (the tested version is pinned in `requirements.txt`)
- MongoDB >= 4.4, configured as the `rs01` replica set
- pymongo
- motor
- praw

## Installation and checks

Run these commands from the repository directory:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -v
```

Use a fresh virtual environment when upgrading from the old requirements, which
included Red-DiscordBot and incompatible dependency pins. The test suite loads
the real Discord.py extensions without connecting to Discord, Reddit, or MongoDB.
It does not verify production credentials, database connectivity, or permissions.

For functional scenarios, branch coverage, and optional real-MongoDB integration
checks, see [TESTING.md](TESTING.md). Install `requirements-dev.txt` and run
`.venv/bin/python -m coverage run -m unittest discover -v`, followed by
`.venv/bin/python -m coverage report`, to enforce the coverage check locally.

In the [Discord Developer Portal](https://discord.com/developers/applications),
select the application, open **Bot**, and enable **Server Members Intent** and
**Message Content Intent** under **Privileged Gateway Intents**. The code requests
both intents; they must also be enabled in the portal.

Install the app in the server named by `DISCORD_SERVER_ID` with the `bot` and
`applications.commands` OAuth2 scopes. Discord includes `applications.commands`
with the `bot` scope by default; check the app's installation settings if command
registration fails. See [Discord's application command documentation](https://docs.discord.com/developers/interactions/application-commands).

Set the environment variables below in the bot's service environment, then start
the bot with `.venv/bin/python bot.py` from the repository directory. Startup
creates `logs/`, loads the extensions listed in `config.json`, and syncs the slash
commands to `DISCORD_SERVER_ID` before connecting to the gateway. An extension or
command-sync failure is logged and stops startup. Restart the bot after deploying
these changes so Discord receives the command definitions.

## Slash commands

All commands use `/` and appear in Discord's command picker in the configured
server. Text commands such as `!verify` are retired; `DISCORD_PREFIX` no longer
controls commands. Use `/help` to see the available commands.

| Command | Purpose |
|---|---|
| `/verify` or `/verification` | Open the verification website |
| `/status` | Show your stored verification status |
| `/whois user:<name, ID, or mention>` | Look up a linked Discord/Reddit account |
| `/editflair user:<user> flair:<choice>` | Update trade flair; requires the updater role |
| `/removeuser user:<user>` or `/remove_user` | Remove a verification record after confirmation; requires the updater role |
| `/notes view user:<member>` | View moderator notes |
| `/notes find note_hash:<hash>` | Find a note by hash |
| `/notes create user:<member> note_content:<text>` | Save a moderator note; `/notes add` and `/notes new` are aliases |
| `/notes delete note_hash:<hash>` | Delete a note after confirmation; `/notes remove` is an alias |
| `/limiter whitelist member:<member> seconds:<duration>` | Temporarily exempt a member from the posting limit |
| `/search search_term:<product>` | Search CeX |
| `/check search_term:<product>` | Check eBay sold prices; `/pc`, `/chk`, `/price`, and `/pricecheck` are aliases |
| `/mot registration:<plate> year:<optional year>` | Look up MOT history |
| `/usl username:<Reddit username>` | Query the Universal Scammer List |
| `/rd` or `/wa` | Send a meme, when the optional `rendermeme` extension is loaded |
| `/load extension:<name>`, `/unload extension:<name>`, `/reload extension:<name>` | Manage extensions; bot owner only |

The `/notes` and `/limiter whitelist` commands require Manage Roles permission.
Extension management replies are private and report success after both the
extension operation and slash-command sync finish. CeX, notes, MOT, and help
results use arrow buttons for pagination; only the requesting user can change
pages, and the buttons are disabled when the menu expires.

## Environment variables

| Name | Purpose | Required | Default value |
|---|---|---|---|
| `MONGODB_HOST` | The hostname of the MongoDB instance to connect to | No | `127.0.0.1` |
| `MONGODB_PORT` | The port on which the MongoDB instance is listening | No | `27017` |
| `MONGODB_USERNAME` | The username with which to authenticate with MongoDB | Yes | |
| `MONGODB_PASSWORD` | The password with which to authenticate with MongoDB | Yes | |
| `MONGODB_DATABASE` | The name of the database in MongoDB to read/write data | No | `hwsuk` |
| `DISCORD_SERVER_ID` | The server where slash commands are registered and member roles are managed | Yes | |
| `DISCORD_TOKEN` | The application's Discord bot token | Yes | |
| `PRAW_CLIENT_ID` | The client ID for the application used for PRAW queries | Yes | |
| `PRAW_CLIENT_SECRET` | The client secret for the application used for PRAW queries | Yes | |
| `PRAW_PASSWORD` | The password for the user used for PRAW queries | Yes | |
| `PRAW_USER_AGENT` | The user agent sent to Reddit when making PRAW queries | No | `Checks if users are banned for our synced discord and keeps flairs synced` |
| `PRAW_USERNAME` | The username of the user used for PRAW queries | No | `HWSUKMods` |
| `REACTION_CHANNEL_ID` | The channel ID used for feedback | Yes | |
| `MOD_CHANNEL_ID` | The channel ID used for mod notifications of feedback items | Yes | |
| `REACTION_THRESHOLD` | Determines how many upvotes a feedback submission needs before it is sent to the mods | Yes | |
| `BUY_SELL_CHANNEL_ID` | The channel ID used for removing too frequent posts | Yes | |
| `BUY_SELL_BACKUP_DM_CHANNEL_ID` | The channel ID used for notifying users of removed posts if they have DMs disabled | No | `292032782409007115` |
| `BUY_SELL_LIMIT_SECONDS` | The number of seconds that each user post is limited to | Yes | `259200` |
| `DVLA_API_KEY` | Key for the DVLA API | Yes | |
| `LOGGING_FILENAME` | Determines the naming format used for log files | No | `f'bot-{datetime.now().strftime("%m-%d-%Y-%H%M%S")}.log'` |
