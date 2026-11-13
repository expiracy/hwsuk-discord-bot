import discord
import asyncio
from datetime import timedelta
import sys
import logging
from discord.ext import commands
from unity_util import bot_config

green = 0x00ff00


class Feedback(commands.Cog):

    def __init__(self, client):
        self.client = client
        self._notified = {}
        self._notification_lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_ready(self):
        print('Feedback cog online')

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.channel.id == bot_config.REACTION_CHANNEL_ID and message.author.id != self.client.user.id:
            await message.add_reaction('👍')
            await message.add_reaction('👎')

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not payload.guild_id or payload.channel_id != bot_config.REACTION_CHANNEL_ID:
            return
        if payload.emoji.name != '👍' or payload.user_id == self.client.user.id:
            return
        if getattr(payload, 'member', None) and payload.member.bot:
            return
        channel = self.client.get_channel(payload.channel_id)
        if channel is None:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            logging.warning('Could not fetch feedback message %s', payload.message_id)
            return
        cutoff = discord.utils.utcnow() - timedelta(days=1)
        if message.author.bot or message.created_at < cutoff:
            return
        for reaction in message.reactions:
            if str(reaction.emoji) == '👍' and reaction.count - int(reaction.me) >= bot_config.REACTION_THRESHOLD:
                async with self._notification_lock:
                    self._notified = {key: created for key, created in self._notified.items() if created >= cutoff}
                    if message.id not in self._notified and await self.send_feedback_embed(message):
                        self._notified[message.id] = message.created_at
                return

    async def send_feedback_embed(self, message):
        if message.author.id == self.client.user.id:
            return

        channel = self.client.get_channel(bot_config.MOD_CHANNEL_ID)

        if not channel:
            logging.warning("WARNING: Tried to send an embed to a nonexistent channel.")
            return

        link = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"
        embed = discord.Embed(description=f"_You were notified about this feedback because it received at least {bot_config.REACTION_THRESHOLD} upvotes._",
                              color=green)
        embed.set_author(name="New feedback received", url=link)
        embed.add_field(name="Feedback", value=message.content[:1024] or '(no text)')

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logging.warning('Could not deliver feedback notification for message %s', message.id)
            return False
        return True

async def setup(client):
    await client.add_cog(Feedback(client))
