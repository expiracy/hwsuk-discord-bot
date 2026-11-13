import json
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import motor.motor_asyncio
from datetime import datetime as dt
import logging
import re
import praw
from unity_util import bot_config
from unity_util.menus import clear_reactions
from unity_util.slash_commands import command_alias, command_context
from unity_services import universal_scammer_list as usl
import sys

with open('config.json', 'r') as f:
    conf = json.load(f)

reddit = praw.Reddit(client_id=bot_config.PRAW_CLIENT_ID, client_secret=bot_config.PRAW_CLIENT_SECRET,
                     username=bot_config.PRAW_USERNAME, password=bot_config.PRAW_PASSWORD, user_agent=bot_config.PRAW_USER_AGENT)

mongo = motor.motor_asyncio.AsyncIOMotorClient(host=bot_config.MONGODB_HOST, port=int(
    bot_config.MONGODB_PORT), replicaSet="rs01", username=bot_config.MONGODB_USERNAME, password=bot_config.MONGODB_PASSWORD, authSource=bot_config.MONGODB_DATABASE, authMechanism='SCRAM-SHA-1')
db = mongo[bot_config.MONGODB_DATABASE]


class Verify(commands.Cog):

    def __init__(self, client):
        self.client = client
        self._queue_lock = asyncio.Lock()
        self.monitor_db.start()

    def cog_unload(self):
        self.monitor_db.cancel()

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print('Verify cog online')
        await self.monitor_db()


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        data = await db.users.find_one({"discord.id": str(member.id)})

        if(data and data.get("verified")):  # Check if user has verified online first
            await self.set_verified(member.id)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if guild.id != int(bot_config.DISCORD_SERVER_ID):
            return
        await db.users.find_one_and_update({"discord.id": str(user.id)}, {"$set": {"verified": False, "banned": True}})
        logging.info('Banned Discord user %s in guild %s', user.id, guild.id)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        if guild.id != int(bot_config.DISCORD_SERVER_ID):
            return
        await db.users.find_one_and_update({"discord.id": str(user.id)}, {"$set": {"banned": False}})
        logging.info(f'UNBANNED {user.name}#{user.discriminator} ON {guild.name}')

    # Commands

    @app_commands.command()
    async def verify(self, interaction: discord.Interaction):
        """Instructions on how to verify"""
        ctx = await command_context(interaction)
        embed = discord.Embed(
            title='Verify here!',
            url='https://verify.hardwareswap.uk'
        )
        await ctx.send(embed=embed)

    verification = command_alias(verify, 'verification')

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(user="Discord ID, mention, username, or Reddit username")
    async def whois(self, interaction: discord.Interaction, user: str):
        """Search by Discord username, ID, mention or Reddit username for a verified hwsuk user"""
        ctx = await command_context(interaction)
        # The slash option accepts Discord IDs, mentions, and Reddit/Discord names.
        user_data = await self.get_user(user)
        if not user_data:
            user = user.replace('`', '``')
            embed = discord.Embed(title = "Whois results:", description=f"No results found for {user}")
            await ctx.send(embed=embed)
            return
        else:
            embed = await self.make_whois_embed(user_data)
            await ctx.send(embed=embed)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(user="Discord ID, mention, username, or Reddit username", flair="Trade flair to assign")
    @app_commands.choices(flair=[app_commands.Choice(name=value, value=value) for value in conf['flairs']])
    async def editflair(self, interaction: discord.Interaction, user: str, flair: str):
        """Edit a user's trade role/flair"""
        ctx = await command_context(interaction)
        if int(bot_config.DISCORD_UPDATER_ROLE) not in [i.id for i in ctx.author.roles]:
            desc = "Hey, looks like you don't have permission to do this!\nPlease contact a mod if you feel should have this permission"
            embed = discord.Embed(description=desc, colour=ctx.guild.me.colour)
            await ctx.send(embed=embed)
            return

        user_data = await self.get_user(user)

        if not user_data:
            user = user.replace('`', '``')
            embed = discord.Embed(description=f"No results found for {user}")
            await ctx.send(embed=embed)
            return

        if flair not in conf['flairs']:
            embed = discord.Embed(
                description=f"Flair {flair} not found 🙁".replace('`', '``'),
                color=ctx.guild.me.colour
            )
            await ctx.send(embed=embed)
            return

        # set flair and new role
        if await self.set_trade_flair(user_data, flair) == True:
            desc = [f"✅ Flair set successfully for {user_data['reddit']['name']}"]
        else:
            desc = [
                f"❌ Error setting trade flair for {user_data['reddit']['name']}"]
        # Set the discord role
        if await self.set_trade_role(user_data, flair) == True:
            await self.remove_trades(user_data['discord']['id'], keep_role=int(conf['flairs'][flair]['rid']))
            desc.append(
                f"✅ Role set successfully for <@{user_data['discord']['id']}>")
        else:
            desc.append(
                f"❌ Error setting trade role for <@{user_data['discord']['id']}>")

        embed = discord.Embed(description="\n".join(desc))
        await ctx.send(embed=embed)

    @app_commands.command()
    async def status(self, interaction: discord.Interaction):
        """Show your verification status"""
        ctx = await command_context(interaction)
        user_data = await self.get_user(str(ctx.author.id))
        if not user_data:
            embed = discord.Embed(
                description="Looks like you're not verified. Please [verify here!](https://verify.hardwareswap.uk)")
            embed.set_author(name="User not found 🙁")
            await ctx.send(embed=embed)
            return
        embed = discord.Embed(
            title="Verification status"
        )
        embed.add_field(
            name="Discord",
            value=f"<@{user_data['discord']['id']}>",
            inline=True
        )
        embed.add_field(
            name="Reddit",
            value=f"u/{user_data['reddit']['name']}",
            inline=True
        )
        embed.add_field(
            name="Verified",
            value=user_data['verified'],
            inline=True
        )
        days_ago = dt.now() - dt.fromtimestamp(user_data['verified_at'])
        embed.set_footer(text=f"Verified {days_ago.days} days ago")
        await ctx.send(embed=embed)

    @app_commands.command(name='removeuser')
    @app_commands.guild_only()
    @app_commands.describe(user="Discord ID, mention, username, or Reddit username")
    async def remove_user(self, interaction: discord.Interaction, user: str):
        """Removes a user from the verification database"""
        ctx = await command_context(interaction)
        if int(bot_config.DISCORD_UPDATER_ROLE) not in [i.id for i in ctx.author.roles]:
            desc = "Hey, looks like you don't have permission to do this!\nPlease contact a mod if you feel should have this permission"
            await ctx.send(embed=discord.Embed(description=desc))
            return
        user_data = await self.get_user(user)
        if not user_data:
            user = user.replace('`', '``')
            embed = discord.Embed(description=f"No results found for `{user}`")
            embed.set_author(name="User not found")
            await ctx.send(embed=embed)
            return
        embed = await self.make_whois_embed(user_data)
        await ctx.send(embed=embed)
        message_object = await ctx.send('Are you sure you want to remove this user from the database?')
        emojis = ['✅', '❌']
        for i in emojis:
            await message_object.add_reaction(i)
        def reaction_check(reaction, user):
            return (user == ctx.author) and (reaction.message.id == message_object.id) and (reaction.emoji in emojis)
        try:
            reaction, user = await self.client.wait_for('reaction_add', timeout=120.0, check=reaction_check)
        except asyncio.TimeoutError:
            await clear_reactions(message_object)
            return
        else:
            # The user has reacted with an emoji in the list, let's find out which one
            if reaction.emoji == '❌':
                await clear_reactions(message_object)
                return
            if reaction.emoji == '✅':  # Execute order 66
                try:
                    server = self.client.get_guild(int(bot_config.DISCORD_SERVER_ID))
                    member = server.get_member(int(user_data['discord']['id']))
                    verified_role = server.get_role(int(bot_config.DISCORD_VERIFIED_ROLE))
                    await member.remove_roles(verified_role)
                    await db.users.delete_one({"discord.id": str(user_data['discord']['id'])})
                    logging.info('Removed Discord user %s from verification', user_data['discord']['id'])
                    embed = discord.Embed(description=f"User <@{user_data['discord']['id']}> removed from the database successfully 🤠")
                    await ctx.send(embed=embed)
                except Exception as err:
                    logging.error(f"ERROR REMOVING USER: {err}")
                    await ctx.send("Couldn't remove the user from the database for some reason. Please consult the logs for more details")

    remove_user_alias = command_alias(remove_user, 'remove_user')

    # Helper functions

    # Useful for verification event
    async def set_verified(self, member_id):
        # Get guild object from ID
        server = self.client.get_guild(int(bot_config.DISCORD_SERVER_ID))
        if server is None:
            return False
        # Get role object of verified role by ID
        role = server.get_role(int(bot_config.DISCORD_VERIFIED_ROLE))
        if role is None:
            return False
        # Get member object by discord user ID
        member = server.get_member(int(member_id))
        if member is None:
            try:
                member = await server.fetch_member(int(member_id))
            except discord.HTTPException:
                return False

        if member:  # Someone might verify before they join the server
            if role in member.roles:
                return True
            try:
                await member.add_roles(role)  # Add user as verified
            except discord.HTTPException:
                logging.exception('Could not assign verified role to Discord user %s', member_id)
                return False
            try:
                await member.send("Congratulations! You are now verified!")
            except discord.HTTPException:
                logging.warning('Could not DM verified Discord user %s', member_id)
            return True
        return False

    # Useful for whois and editflair
    async def get_user(self, user: str) -> dict:
        mention = re.fullmatch(r'<@!?(\d+)>', user)
        if mention:
            user = mention.group(1)
        discord_discrim_regex = re.compile(r"[\w]*#[0-9]{4}")  # eg. issy#4200
        if user.isdigit() and len(user) > 15:  # eg. 377212919068229633
            user_type = 'discord.id'
        # eg. /u/issythegurl or u/issythegurl
        elif user.startswith('u/') or user.startswith('/u/'):
            user = user.split('u/')[1]
            user_type = 'reddit.name'
        elif discord_discrim_regex.match(user) != None:
            user_type = 'discord.name'
        else:
            # Guess if it's a Reddit or Discord user
            for i in ['reddit.name','discord.username']:
                data = await db.users.find_one({f"{i}": {"$regex": f"^{re.escape(user)}$", "$options": "i"}})
                if data:
                    return data
                else:
                    continue
            if not data:
                return {}
        data = await db.users.find_one({f"{user_type}": {"$regex": f"^{re.escape(user)}$", "$options": "i"}})
        if data:
            return data
        return {}

    # Used for the whois commmand
    async def make_whois_embed(self, user_data: dict) -> discord.Embed:
        embed = discord.Embed()
        embed.set_author(name='Whois results:')
        embed.add_field(
            name='Discord', value=f"<@{user_data['discord']['id']}>", inline=True)
        embed.add_field(
            name='Reddit', value=f"[u/{user_data['reddit']['name']}](https://www.reddit.com/user/{user_data['reddit']['name']})", inline=True)
        trades = await self.get_trades(user_data['discord']['id'])
        if trades:
            embed.add_field(name='Trades', value=trades, inline=False)
        usl_status = await usl.fetch_usl_user_data(user_data['reddit']['name'])
        embed.add_field(name="On USL", value="Unknown - USL API unavailable", inline=True)
        days_ago = dt.now() - dt.fromtimestamp(user_data['verified_at'])
        embed.set_footer(text=f"Verified {days_ago.days} days ago")
        return embed

    # Used in for whois and editflair
    async def get_trades(self, discord_id: str) -> str:
        """Get the trade role of a member"""
        trade_roles = {int(item['rid']) for item in conf['flairs'].values()}
        guild = self.client.get_guild(int(bot_config.DISCORD_SERVER_ID))
        member = guild.get_member(int(discord_id)) if guild else None
        if member is None:
            return None
        # returns all roles in member, lowest in hierarchy first
        return next((role.name for role in reversed(member.roles) if role.id in trade_roles), None)

    # Used in editflair
    async def remove_trades(self, discord_id: int, keep_role=None):
        """Remove all trade roles from a member"""
        # Get guild object from ID
        server = self.client.get_guild(int(bot_config.DISCORD_SERVER_ID))
        # Get member object by discord user ID
        member = server.get_member(int(discord_id))
        trade_roles = {int(item['rid']) for item in conf['flairs'].values()}
        member_trade_roles = [i for i in member.roles if i.id in trade_roles and i.id != keep_role]
        if member_trade_roles:
            for role in member_trade_roles:
                await member.remove_roles(role)

    # Useful for editflair
    async def set_trade_flair(self, user_data, flair):
        try:
            flair_text = f"{flair} Trades"
            await asyncio.to_thread(reddit.subreddit("hardwareswapuk").flair.set,
                                    user_data["reddit"]["name"], flair_text,
                                    css_class=flair_text.replace("+", ""))
        except Exception as err:
            logging.error(
                f"ERROR SETTING FLAIR FOR {user_data['reddit']['name']}: {err}"
            )
            return False
        return True

    # Useful for editflair
    async def set_trade_role(self, user_data, flair):
        # Get guild object from ID
        server = self.client.get_guild(int(bot_config.DISCORD_SERVER_ID))
        # Get role object of verified role by ID
        role = server.get_role(int(conf['flairs'][flair]['rid']))
        if role is None:
            return False
        # Get member object by discord user ID
        member = server.get_member(int(user_data['discord']['id']))
        if member is None:
            return False
        try:
            await member.add_roles(role)
            return True
        except Exception as err:
            logging.error(
                f"ERROR ADDING ROLE FOR {member.name}#{member.discriminator} IN {server.name}: {err}"
            )
            return False

    # Tasks

    @tasks.loop(seconds=20)
    async def monitor_db(self):
        """Monitor DB for changes"""
        async with self._queue_lock:
            await self.process_queue()

    async def process_queue(self):
        try:
            n = await db.queue.count_documents({})
            if n == 0:
                return
            data = db.queue.find()
            data.limit(n)
            async for document in data:
                try:
                    user = await db.users.find_one({"_id": document['ref']})
                    if not user or not user.get('discord', {}).get('id'):
                        logging.warning('Verification queue entry %s has no valid user', document.get('_id'))
                        continue
                    if await self.set_verified(user['discord']['id']):
                        await db.queue.find_one_and_delete({'_id': document['_id']})
                        logging.info('Verified Discord user %s', user['discord']['id'])
                except Exception:
                    logging.exception('Failed verification queue entry %s', document.get('_id'))
        except Exception as err:
            logging.error(f'ERROR MONITORING DB: {err}')

    @monitor_db.before_loop
    async def before_monitor_db(self):
        await self.client.wait_until_ready()


async def setup(client):
    await client.add_cog(Verify(client))
