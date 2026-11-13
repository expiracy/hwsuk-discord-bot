# HWSUK Discord Bot

## Deployment requirements

- Python >= 3.11
- discord.py 2.x (the tested version is pinned in `requirements.txt`)
- systemd
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

In the [Discord Developer Portal](https://discord.com/developers/applications),
select the application, open **Bot**, and enable **Server Members Intent** and
**Message Content Intent** under **Privileged Gateway Intents**. The code requests
both intents; they must also be enabled in the portal.

Set the environment variables below in the bot's service environment, then start
the bot with `.venv/bin/python bot.py` from the repository directory. Startup
creates `logs/` and loads the extensions listed in `config.json` before connecting
to the gateway. An extension failure logs its name and traceback and stops startup.

The owner commands `!load <extension>`, `!unload <extension>`, and
`!reload <extension>` report success after the operation completes. Replace `!`
with `DISCORD_PREFIX` if configured. CeX, notes, and MOT results use arrow buttons
for pagination; only the requesting user can change pages, and the buttons are
disabled when the menu expires.

## Environment variables

| Name | Purpose | Required | Default value |
|---|---|---|---|
| `MONGODB_HOST` | The hostname of the MongoDB instance to connect to | No | `127.0.0.1` |
| `MONGODB_PORT` | The port on which the MongoDB instance is listening | No | `27017` |
| `MONGODB_USERNAME` | The username with which to authenticate with MongoDB | Yes | |
| `MONGODB_PASSWORD` | The password with which to authenticate with MongoDB | Yes | |
| `MONGODB_DATABASE` | The name of the database in MongoDB to read/write data | No | `hwsuk` |
| `DISCORD_SERVER_ID` | The server ID that is checked when modifying roles or searching for members | Yes | |
| `DISCORD_TOKEN` | The application's Discord bot token | Yes | |
| `DISCORD_PREFIX` | The prefix used for text commands | No | `!` |
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
