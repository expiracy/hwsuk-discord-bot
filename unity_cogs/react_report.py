import sys
import motor.motor_asyncio
import logging
import discord
import datetime

from discord.ext import commands
from unity_util import bot_config
from pymongo.errors import DuplicateKeyError


REPORT_EMOJI = "⚠️"

mongo = motor.motor_asyncio.AsyncIOMotorClient(host=bot_config.MONGODB_HOST, port=int(
    bot_config.MONGODB_PORT), replicaSet="rs01", username=bot_config.MONGODB_USERNAME, password=bot_config.MONGODB_PASSWORD, authSource=bot_config.MONGODB_DATABASE, authMechanism='SCRAM-SHA-1')
db = mongo[bot_config.MONGODB_DATABASE]



class ReactReport(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("Reaction report cog online.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        
        if payload.emoji.name != REPORT_EMOJI:
            return

        # Get the required objects from the payload.
        objects = await self.fetch_objects_from_payload(payload)
        if objects is None:
            return
        guild, channel, message = objects

        report_channel = guild.get_channel(bot_config.REPORT_CHANNEL_ID)

        if not report_channel:
            logging.warning(f"React Report: failed to fetch report output channel with ID {bot_config.REPORT_CHANNEL_ID}")
            return

        cur_time = discord.utils.utcnow()
        timestamp = cur_time.strftime("%d/%m/%Y %H:%M:%S")

        data = {
            "message_id": payload.message_id,
            "reporter_id": payload.user_id,
            "channel_id": payload.channel_id,
            "message_content": message.clean_content,
            "report_timestamp": cur_time
        }

        logging.info(f"Saving report data, message ID: {payload.message_id}")

        save_success = await self.save_report_data(data)

        if save_success:
            await report_channel.send(embed=self.create_new_report_embed(message, channel, payload, timestamp))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        if payload.emoji.name != REPORT_EMOJI:
            return

        # Get the required objects from the payload.
        objects = await self.fetch_objects_from_payload(payload)
        if objects is None:
            return
        guild, channel, message = objects

        for reaction in message.reactions:
            if str(reaction.emoji) == REPORT_EMOJI:
                return

        report_channel = guild.get_channel(bot_config.REPORT_CHANNEL_ID)

        if not report_channel:
            logging.warning(f"React Report: failed to fetch report output channel with ID {bot_config.REPORT_CHANNEL_ID}")
            return

        if await self.remove_report_data(payload.message_id):
            await report_channel.send(embed=self.create_retracted_report_embed(message))

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None:
            return
        report_channel = message.guild.get_channel(bot_config.REPORT_CHANNEL_ID)

        if not report_channel:
            logging.warning(f"React Report: failed to fetch report output channel with ID {bot_config.REPORT_CHANNEL_ID}")
            return

        has_removed = await self.remove_report_data(message.id)
        if has_removed:
            await report_channel.send(embed=self.create_deleted_report_embed(message))

    # Save report data to mongo
    async def save_report_data(self, data: dict):
        try:
            result = await db.reports.update_one(
                {"message_id": data["message_id"]},
                {"$setOnInsert": {**data, "_id": data["message_id"]}}, upsert=True)
        except DuplicateKeyError:
            return False
        return result.upserted_id is not None

    async def remove_report_data(self, message_id: int):
        return await db.reports.find_one_and_delete({"message_id": message_id})

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        if not payload.guild_id:
            return
        guild = self.client.get_guild(payload.guild_id)
        channel = guild.get_channel(bot_config.REPORT_CHANNEL_ID) if guild else None
        if channel is None:
            return
        report = await self.remove_report_data(payload.message_id)
        if report:
            await channel.send(embed=discord.Embed(
                title='Reported message deleted', colour=discord.Colour.green(),
                description=report.get('message_content', '')[:4096]))

    async def fetch_objects_from_payload(self, payload: discord.RawReactionActionEvent):
        guild = self.client.get_guild(payload.guild_id)

        if not guild:
            logging.warning(f"React Report: failed to fetch guild with ID {payload.guild_id}")
            return

        channel = guild.get_channel(payload.channel_id)

        if not channel:
            logging.warning(f"React Report: failed to fetch channel with ID {payload.channel_id}")
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            logging.warning('React Report: could not fetch message %s', payload.message_id)
            return

        if not message:
            logging.warning(f"React Report: failed to fetch message with ID {payload.message_id}")
            return

        return guild, channel, message

    def create_new_report_embed(self, message: discord.Message, channel: discord.TextChannel, payload: discord.RawReactionActionEvent, timestamp: str):
        # Fetch the user who reported the message.
        member = message.guild.get_member(payload.user_id)

        embed = discord.Embed(title="New report created", colour=discord.Colour.orange())
        embed.description = message.clean_content
        embed.add_field(name="Reporter", value=member.mention if member else f'<@{payload.user_id}>')
        embed.add_field(name="Channel", value=f"<#{channel.id}>")
        embed.add_field(name="Timestamp", value=timestamp)
        embed.add_field(name="Message Link", value=f"[Here!]({message.jump_url})")

        return embed

    def create_retracted_report_embed(self, message: discord.Message):
        return discord.Embed(title="Report retracted", colour=discord.Colour.green(), description=message.clean_content)

    def create_deleted_report_embed(self, message: discord.Message):
        return discord.Embed(title="Reported message deleted", colour=discord.Colour.green(), description=message.clean_content)

async def setup(client):
    await client.add_cog(ReactReport(client))
