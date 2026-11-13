import discord
from discord import app_commands
import asyncio
import sys
import logging
from discord.ext import commands
from unity_util import bot_config
import motor.motor_asyncio
import time
from datetime import datetime as dt
import random
import string
from typing import Tuple
from unity_util.menus import clear_reactions, menu
from unity_util.slash_commands import command_alias, command_context

mongo = motor.motor_asyncio.AsyncIOMotorClient(host=bot_config.MONGODB_HOST, port=int(
    bot_config.MONGODB_PORT), replicaSet="rs01", username=bot_config.MONGODB_USERNAME, password=bot_config.MONGODB_PASSWORD, authSource=bot_config.MONGODB_DATABASE, authMechanism='SCRAM-SHA-1')
db = mongo[bot_config.MONGODB_DATABASE]


class Notes(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print('Notes cog online')

# Commands

    notes = app_commands.Group(
        name='notes', description='Manage moderator notes about users',
        guild_only=True, default_permissions=discord.Permissions(manage_roles=True)
    )

    @notes.command()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def view(self, interaction: discord.Interaction, user: discord.Member):
        """View notes for a user"""
        ctx = await command_context(interaction)
        notes = await self.get_notes(str(user.id))

        if not notes:
            await self.no_results(ctx)
            return
        elif len(notes) == 1:
            embed = self.make_note_embed(note=notes[0], colour=ctx.guild.me.colour)
            await ctx.send(embed=embed)
            return

        embeds = [self.make_note_embed(notes[i], {'current': i, 'max': len(notes) - 1}, ctx.guild.me.colour) for i in range(len(notes))]
        embeds.reverse() # Sort newest first
        await menu(ctx, pages=embeds, page=0, timeout=180)

    @notes.command()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def find(self, interaction: discord.Interaction, note_hash: str):
        """Find user note by hash"""
        ctx = await command_context(interaction)
        note_hash = note_hash.lower()
        if len(note_hash) != 7:
            embed = discord.Embed(title="❌ That doesn't look like a valid note hash", colour=ctx.guild.me.colour)
            await ctx.send(embed=embed)
            return
        data = await db.notes.find_one({'hash': note_hash})
        if data is None:
            await ctx.send(embed=discord.Embed(title='No note found with this hash', colour=ctx.guild.me.colour))
            return
        embed = self.make_note_embed(note=data, colour=ctx.guild.me.colour)
        await ctx.send(embed=embed)

    @notes.command()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def delete(self, interaction: discord.Interaction, note_hash: str):
        """Delete a user note"""
        ctx = await command_context(interaction)
        note_hash = note_hash.lower()
        if len(note_hash) != 7:
            embed = discord.Embed(description="❌ That doesn't look like a valid note hash", colour=ctx.guild.me.colour)
            await ctx.send(embed=embed)
            return
        note = await db.notes.find_one({"hash": note_hash})
        if not note:
            embed = discord.Embed(description="❌ No note found with this hash", colour=ctx.guild.me.colour)
            await ctx.send(embed=embed)
            return
        embed = self.make_note_embed(note=note, colour=ctx.guild.me.colour)
        await ctx.send(embed=embed)
        messageObject = await ctx.send('Are you sure you want to remove this note from the database?')
        emojis = ['✅', '❌']
        for i in emojis:
            await messageObject.add_reaction(i)

        def reaction_check(reaction, user):
            return user == ctx.author and reaction.message.id == messageObject.id and reaction.emoji in emojis

        try:
            reaction, user = await self.client.wait_for('reaction_add', timeout=180.0, check=reaction_check)
        except asyncio.TimeoutError:
            await clear_reactions(messageObject)
            return
        else:
            # The user has reacted with an emoji in the list, let's find out which one
            if reaction.emoji == '❌':
                await clear_reactions(messageObject)
                return
            if reaction.emoji == '✅':  # Execute order 66
                try:
                    await clear_reactions(messageObject)
                    await db.notes.delete_one({"hash": note_hash})
                    logging.info(f"Removed user note {note_hash} from the database")
                    embed = discord.Embed(description=f"User note with hash `{note_hash}` removed from the database successfully 🤠", colour=ctx.guild.me.colour)
                    await ctx.send(embed=embed)
                except Exception as err:
                    logging.error(f"ERROR REMOVING NOTE: {err}")
                    await ctx.send("Couldn't remove the note from the database for some reason. Please consult the logs for more details")

    remove = command_alias(delete, 'remove')

    @notes.command()
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.describe(user="Member the note concerns", note_content="The moderator note to save")
    async def create(self, interaction: discord.Interaction, user: discord.Member, note_content: str):
        """Create a note about a user"""
        ctx = await command_context(interaction)
        if not note_content.strip():
            await ctx.send('Please enter note content.')
            return
        note = {'user': str(user.id),
        'content': note_content,
        'added_by': str(ctx.author.id),
        'hash': await self.gen_hash(),
        'date_added': int(time.time())}
        try:
            await db.notes.insert_one(note)
            logging.info(f"Added user note {note['hash']} to the database")
            embed = self.make_note_embed(note=note, colour=ctx.guild.me.colour)
            await ctx.send(content="Saved note successfully 🤠", embed=embed)
        except Exception as err:
            logging.error(f"ERROR ADDING NOTE: {err}")
            await ctx.send("Couldn't add the note to the database for some reason. Please consult the logs for more details")

    add = command_alias(create, 'add')
    new = command_alias(create, 'new')

# Helper functions

    def make_note_embed(self, note: dict, index: dict = {}, colour: discord.Colour = 0) -> discord.Embed:
        """Construct embed from note"""
        content = f"**Notes for <@{note['user']}>**\n{note['content']}"
        embed = discord.Embed(description=content if len(content) <= 4096 else content[:4093] + '...', colour=colour)
        date = dt.fromtimestamp(note['date_added'])
        embed.add_field(name='Date Added', value=f"{date.day}/{date.month}/{date.year}", inline=True)
        embed.add_field(name='Added by', value=f"<@{note['added_by']}>", inline=True)
        embed.add_field(name='Hash', value=f"`{note['hash']}`", inline=True)
        if index:
            embed.set_footer(text=f"{index['current'] + 1} of {index['max'] + 1}")
        return embed

    async def get_notes(self, user_id: str) -> Tuple[dict]:
        """Retrieve notes from DB by user ID"""
        n = await db.notes.count_documents({"user": user_id})
        if n == 0:
            return ()
        data = db.notes.find({"user": user_id})
        notes = []
        data.limit(n)
        async for note in data:
            notes.append(note)
        return tuple(notes)

    # Used in create command
    async def gen_hash(self) -> str:
        """Generate unique hash for a note"""
        unique = False
        while not unique:
            note_hash = ''.join(random.choice(string.ascii_lowercase+string.digits) for i in range(7))
            data = await db.notes.find_one({'hash': note_hash})
            if not data:
                return note_hash

    async def no_results(self, ctx):
        embed = discord.Embed(description="❌ No notes found for this user", colour=ctx.guild.me.colour)
        await ctx.send(embed=embed)

async def setup(client):
    await client.add_cog(Notes(client))
