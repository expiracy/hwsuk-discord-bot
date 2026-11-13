import discord
from discord import app_commands
from discord.ext import commands
import datetime
import humanize
from unity_util import bot_config
from unity_util.slash_commands import command_context
import logging
import asyncio
import sys


class Limiter(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.whitelisted_users = []

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print('Buy-sell-trade post limiter cog online')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # we do not want the bot to reply to itself or other bots
        if message.author.bot == True or message.author.id == self.client.user.id:
            return

        # Only read messages in the right channel
        if message.channel.id != bot_config.BUY_SELL_CHANNEL_ID:
            return

        author = message.author
        if author.id in self.whitelisted_users:
            return
        content = message.content # Save this
        time_limit = discord.utils.utcnow() - datetime.timedelta(seconds=bot_config.BUY_SELL_LIMIT_SECONDS)
        async for past_message in message.channel.history(after=time_limit, limit=None):
            if past_message.author == author and past_message.id != message.id:
                deletion_success = False
                try:
                    logging.info(f"Deleting message {message.id} from {author.id}")
                    await message.delete()
                    deletion_success = True
                except discord.Forbidden:
                    logging.warning(f"Did not have permission to delete message {message.id} from {author}!")
                except discord.NotFound:
                    logging.info(f"Message {message.id} from {author.id} was already deleted")
                except discord.HTTPException as e:
                    logging.error(f"Failed to delete message {message.id} from {author.id} : {e}")

                if deletion_success:
                    await self.send_info_message(author, message.channel.id, content, past_message.created_at)
                return

    limiter = app_commands.Group(
        name='limiter', description='Manage the buy-sell-trade posting limit',
        guild_only=True, default_permissions=discord.Permissions(manage_roles=True)
    )

    @limiter.command()
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.describe(member="Member allowed to post", seconds="Duration of the exemption in seconds")
    async def whitelist(self, interaction: discord.Interaction, member: discord.Member, seconds: int):
        """Allows a user to post in the buy-sell-trade channel within the slowmode time"""
        ctx = await command_context(interaction)
        if seconds <= 0:
            await ctx.send('The whitelist duration must be positive.')
            return
        desc = f"{member.mention} you can now post in <#{bot_config.BUY_SELL_CHANNEL_ID}> for {str(datetime.timedelta(seconds=int(seconds)))}"
        embed = discord.Embed(title=f"Whitelisted user", description=desc, colour=member.colour)
        await ctx.send(embed=embed)
        self.whitelisted_users.append(member.id)
        try:
            await asyncio.sleep(seconds)
        finally:
            try:
                self.whitelisted_users.remove(member.id)
            except ValueError:
                logging.warning(f"User {member.id} already removed from whitelist")

    async def make_embed(self, author: discord.Member, deleted_content: str) -> discord.Embed:
        embed = discord.Embed(description=deleted_content, colour=author.colour)
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
        return embed

    async def send_info_message(self, author: discord.Member, channel_id: int, deleted_content: str, creation_time: datetime):
        limit_timestamp = datetime.timedelta(seconds=bot_config.BUY_SELL_LIMIT_SECONDS)
        post_again_formatted_time = (creation_time + limit_timestamp).strftime("%d/%m/%Y %I:%M:%S %p")

        content = f"Your post in <#{channel_id}> has been removed due to being within {humanize.naturaldelta(limit_timestamp)} of your last post."
        content += f"\nYou may post again at {post_again_formatted_time}."
        content += "\n\nBelow is the message you tried to send:"

        embed = await self.make_embed(author, deleted_content)

        try:
            if author.dm_channel is None:
                await author.create_dm()
            await author.dm_channel.send(content, embed=embed)
        except discord.HTTPException:
            backup_channel = self.client.get_channel(bot_config.BUY_SELL_BACKUP_DM_CHANNEL_ID)
            if backup_channel is None:
                logging.warning('Could not find the limiter notification channel')
                return
            content = f"<@{author.id}> {content}"
            await backup_channel.send(content=content, embed=embed,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=[author], replied_user=False))

async def setup(client):
    await client.add_cog(Limiter(client))
