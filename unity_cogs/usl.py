import re
import sys
import logging
import discord
from discord import app_commands

from discord.ext import commands
from unity_util import bot_config
from unity_util.slash_commands import command_context
from unity_services import universal_scammer_list as usl



EMBED_BANNED_COLOUR = 0xb00e0e
EMBED_NOT_BANNED_COLOUR = 0x3cb00e


class UniversalScammerList(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Universal Scammer List search cog online')

    @app_commands.command(name='usl')
    @app_commands.describe(username="Reddit username to check against the Universal Scammer List")
    async def query_universal_scammer_list(self, interaction: discord.Interaction, *, username: str):
        """
        Queries the Universal Scammer List to get information about a user.
        """
        ctx = await command_context(interaction)

        # Strip the username prefix, if it is present.
        # The USL API request will fail if we pass this in.
        username = username.replace('u/', '')
        username = username.replace('/', '')

        # Check reddit username format.
        regex = re.compile("[A-Za-z0-9_-]+$")

        if not regex.match(username):
            await ctx.send(":warning: Invalid username format. Reddit usernames can consist of alphanumeric characters, hyphens and underscores only.")
            return

        logging.info(f"Received request to check USL for username: {username}")

        try:
            response = await usl.fetch_usl_user_data(username)
            if not isinstance(response, dict) or not isinstance(response.get('banned'), bool) or not response.get('person'):
                await ctx.send('USL is currently unavailable. This user\'s scammer-list status is unknown.')
                return
            await ctx.send(embed=self.make_embed(response))
        except RuntimeError as e:
            logging.warning(f"Error while querying USL API: {e}")
            await ctx.send(":warning: Something went wrong while querying the USL database. Please try again later, or contact the moderators for assistance.")


    def make_embed(self, data: dict) -> discord.Embed:
        embed = discord.Embed(title="USL Search Results", colour=EMBED_BANNED_COLOUR if data["banned"] else EMBED_NOT_BANNED_COLOUR)
        embed.add_field(name="Username", value=f"/u/{data['person']}")
        embed.add_field(name="Banned", value=f"Yes!" if data["banned"] else "No")

        if data["banned"]:
            embed.set_footer(text="⚠️ DO NOT trade with this user! ⚠️")

        return embed


async def setup(client):
    await client.add_cog(UniversalScammerList(client))
