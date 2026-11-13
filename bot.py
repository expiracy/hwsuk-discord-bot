import discord
from discord.ext import commands
import json
import logging
from unity_util import bot_config
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
    async def setup_hook(self):
        for cog in conf['preloaded']:
            extension = f'unity_cogs.{cog}'
            try:
                await self.load_extension(extension)
            except commands.ExtensionError:
                logging.exception('Failed to load extension %s', extension)
                raise


client = UnityBot(command_prefix=bot_config.DISCORD_PREFIX, intents=intents)

@client.event
async def on_ready():
    logging.info(f'Logged in as {client.user.name}, {client.user.id}')
    logging.info('-----------------------------------------')
    await client.change_presence(activity=discord.Game("Verifying 👀"))

@client.command()
@commands.is_owner()
async def load(ctx, extension):
    await client.load_extension(f'unity_cogs.{extension}')
    await ctx.send(f'{extension} loaded')
    logging.info(f'{extension} loaded')

@client.command()
@commands.is_owner()
async def unload(ctx, extension):
    await client.unload_extension(f'unity_cogs.{extension}')
    await ctx.send(f'{extension} unloaded')
    logging.info(f'{extension} unloaded')

@client.command()
@commands.is_owner()
async def reload(ctx, extension):
    await client.reload_extension(f'unity_cogs.{extension}')
    await ctx.send('{} reloaded'.format(extension))
    logging.info(f'{extension} reloaded')

@client.event
async def on_command_error(ctx, error):
    original = getattr(error, 'original', error)
    if isinstance(original, commands.ExtensionError):
        logging.error('Extension operation failed: %s', original,
                      exc_info=(type(original), original, original.__traceback__))
        await ctx.send(f'Extension operation failed: {original}')
        return
    await commands.Bot.on_command_error(client, ctx, error)

def main():
    Path('logs').mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s]\t %(name)s: %(message)s", handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'./logs/{bot_config.LOGGING_FILENAME}')
    ])
    client.run(bot_config.DISCORD_TOKEN, log_handler=None)


if __name__ == '__main__':
    main()
