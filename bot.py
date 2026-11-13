import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import logging
from unity_util import bot_config
from unity_util import health
from unity_util.menus import menu
from unity_util.slash_commands import command_context, is_owner
import sys
from pathlib import Path

with open('config.json', 'r') as f:
    conf = json.load(f)

intents = discord.Intents(
    guilds=True,
    members=True,
    bans=True,
    emojis=True,
    messages=True,
    message_content=True,
    guild_messages=True,
    dm_messages=True,
    reactions=True,
    guild_reactions=True,
    dm_reactions=True
)

class UnityBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gateway_connected = False

    async def setup_hook(self):
        for cog in conf['preloaded']:
            extension = f'unity_cogs.{cog}'
            try:
                await self.load_extension(extension)
            except commands.ExtensionError:
                logging.exception('Failed to load extension %s', extension)
                raise
        await self.sync_commands()
        if bot_config.BOT_HEALTH_FILE:
            self.heartbeat.start()

    @tasks.loop(seconds=15)
    async def heartbeat(self):
        try:
            health.record(bot_config.BOT_HEALTH_FILE, self.gateway_connected)
        except OSError:
            logging.warning('Could not update the container heartbeat')

    async def close(self):
        self.heartbeat.cancel()
        if bot_config.BOT_HEALTH_FILE:
            try:
                Path(bot_config.BOT_HEALTH_FILE).unlink(missing_ok=True)
            except OSError:
                logging.warning('Could not remove the container heartbeat')
        await super().close()

    async def sync_commands(self):
        guild = discord.Object(id=int(bot_config.DISCORD_SERVER_ID))
        self.tree.copy_global_to(guild=guild)
        try:
            await self.tree.sync(guild=guild)
        except discord.HTTPException:
            logging.exception('Failed to sync slash commands for guild %s', guild.id)
            raise


client = UnityBot(command_prefix=commands.when_mentioned, intents=intents, help_command=None,
                  allowed_mentions=discord.AllowedMentions.none())


@client.tree.command(name='help', description='Show the available slash commands')
async def slash_help(interaction: discord.Interaction):
    ctx = await command_context(interaction)
    available = sorted(
        (command for command in client.tree.walk_commands()
         if isinstance(command, app_commands.Command) and 'alias_for' not in command.extras),
        key=lambda command: command.qualified_name,
    )
    pages = [discord.Embed(
        title='Slash commands',
        description='\n'.join(f'/{command.qualified_name} — {command.description}'
                              for command in available[start:start + 10]),
    ) for start in range(0, len(available), 10)]
    await menu(ctx, pages)

@client.event
async def on_ready():
    client.gateway_connected = True
    logging.info(f'Logged in as {client.user.name}, {client.user.id}')
    logging.info('-----------------------------------------')
    await client.change_presence(activity=discord.Game("Verifying 👀"))

@client.event
async def on_disconnect():
    client.gateway_connected = False

@client.event
async def on_resumed():
    client.gateway_connected = True

@client.tree.command(description='Load an extension (bot owner only)')
@app_commands.check(is_owner)
async def load(interaction: discord.Interaction, extension: str):
    ctx = await command_context(interaction, ephemeral=True)
    await client.load_extension(f'unity_cogs.{extension}')
    await client.sync_commands()
    await ctx.send(f'{extension} loaded')
    logging.info(f'{extension} loaded')

@client.tree.command(description='Unload an extension (bot owner only)')
@app_commands.check(is_owner)
async def unload(interaction: discord.Interaction, extension: str):
    ctx = await command_context(interaction, ephemeral=True)
    await client.unload_extension(f'unity_cogs.{extension}')
    await client.sync_commands()
    await ctx.send(f'{extension} unloaded')
    logging.info(f'{extension} unloaded')

@client.tree.command(description='Reload an extension (bot owner only)')
@app_commands.check(is_owner)
async def reload(interaction: discord.Interaction, extension: str):
    ctx = await command_context(interaction, ephemeral=True)
    await client.reload_extension(f'unity_cogs.{extension}')
    await client.sync_commands()
    await ctx.send('{} reloaded'.format(extension))
    logging.info(f'{extension} reloaded')

@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, 'original', error)
    if isinstance(error, app_commands.CheckFailure):
        message = str(error)
    else:
        logging.error('Slash command failed: %s', original,
                      exc_info=(type(original), original, original.__traceback__))
        if isinstance(original, commands.ExtensionError):
            message = f'Extension operation failed: {original}'
        else:
            message = 'The command failed. Please contact a moderator.'
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)

def main():
    handlers = [logging.StreamHandler(sys.stdout)]
    if bot_config.LOGGING_FILENAME:
        Path('logs').mkdir(exist_ok=True)
        handlers.append(logging.FileHandler(f'./logs/{bot_config.LOGGING_FILENAME}'))
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s]\t %(name)s: %(message)s", handlers=handlers)
    client.run(bot_config.DISCORD_TOKEN, log_handler=None)


if __name__ == '__main__':
    main()
