from discord.ext import commands
import discord
from discord import app_commands
from unity_util import bot_config
from unity_util.slash_commands import command_alias, command_context
import logging
import sys
import random


IMAGE_LINKS = [
    "https://cdn.discordapp.com/attachments/292035708779102208/800403298096119848/eae418cc13c3a477777624169021de320caca7a2827e2dfaf2af21d00f8b1780_1.png",
    "https://tenor.com/view/who-tf-asked-nasas-radar-dish-who-asked-nobody-asked-gif-17675657",
    "https://tenor.com/view/nobody-cares-nobody-asked-who-asked-find-who-asked-searching-gif-19968984",
    "https://tenor.com/view/among-us-who-asked-gif-18850795",
    "https://tenor.com/view/bean-dance-crazy-aye-dats-fr-crazy-hoe-now-show-me-one-person-who-asked-gif-16195074",
    "https://tenor.com/view/who-asked-who-tf-asked-nasa-rocket-bull-crap-who-in-the-heck-asked-gif-18488733",
    "https://tenor.com/view/who-asked-gif-18047968",
    "https://cdn.discordapp.com/attachments/292035708779102208/800517700501372989/image0.gif",
    "https://tenor.com/view/switchasked-gif-19868734",
    "https://tenor.com/view/idid-not-ask-ididnt-ask-ididnt-asked-asked-smh-gif-17286176",
    "https://tenor.com/view/happy-meal-nobody-asked-shut-up-mcdonalds-gif-19269553",
    "https://cdn.discordapp.com/attachments/292035708779102208/800518008350310470/image0.gif",
    "https://cdn.discordapp.com/attachments/292035708779102208/800518008987713597/image1.gif",
    "https://cdn.discordapp.com/attachments/292035708779102208/800518009596674058/image2.gif",
    "https://cdn.discordapp.com/attachments/292035708779102208/800518009948471306/image3.gif",
    "https://tenor.com/view/who-asked-gif-19577763",
    "https://tenor.com/view/who-asked-did-iask-didnt-ask-didnt-gif-19398287",
    "https://tenor.com/view/damn-thats-crazy-who-asked-though-spongebob-dancing-weird-gif-17659544",
    "https://cdn.discordapp.com/attachments/292035708779102208/800518595746201610/image0.gif",
    "https://cdn.discordapp.com/attachments/292035708779102208/800518596509040640/image1.gif",
    "https://cdn.discordapp.com/attachments/292035708779102208/800518596925063168/image2.gif",
    "https://cdn.discordapp.com/attachments/292035708779102208/800519407658467328/image0.gif",
    "https://tenor.com/view/who-the-fuck-asked-maximum-gif-20033803"
]


class RenderMeme(commands.Cog):
    def __init__(self, client):
        self.client = client

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print('Renderdistance meme cog online')

    @app_commands.command(name="rd", description="Send a random meme")
    async def _rd(self, interaction: discord.Interaction):
        ctx = await command_context(interaction)
        await ctx.send(content=random.choice(IMAGE_LINKS))
        return

    wa = command_alias(_rd, 'wa')


async def setup(client):
    await client.add_cog(RenderMeme(client))
