import importlib
import logging
import os
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

import discord
from discord.ext import commands


TEST_ENV = {
    "MONGODB_USERNAME": "test",
    "MONGODB_PASSWORD": "test",
    "DISCORD_SERVER_ID": "1",
    "DISCORD_TOKEN": "test-token",
    "PRAW_CLIENT_ID": "test",
    "PRAW_CLIENT_SECRET": "test",
    "PRAW_PASSWORD": "test",
    "REACTION_CHANNEL_ID": "2",
    "MOD_CHANNEL_ID": "3",
    "REACTION_THRESHOLD": "3",
    "BUY_SELL_CHANNEL_ID": "4",
    "BUY_SELL_LIMIT_SECONDS": "259200",
    "DISCORD_PREFIX": "!",
    "DISCORD_UPDATER_ROLE": "100",
    "DISCORD_VERIFIED_ROLE": "101",
    "EMBED_REMOVER_CHANNEL_ID": "5",
    "REPORT_CHANNEL_ID": "6",
    "MONGODB_HOST": "127.0.0.1",
    "MONGODB_PORT": "27017",
    "MONGODB_DATABASE": "test",
    "PRAW_USERNAME": "tester",
    "PRAW_USER_AGENT": "hwsuk tests",
    "LOGGING_FILENAME": "test.log",
    "DVLA_API_KEY": "test",
}


class BotTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, TEST_ENV))
        self.enterContext(patch("logging.FileHandler", side_effect=lambda *a, **k: logging.NullHandler()))
        self.enterContext(patch("logging.basicConfig"))

    async def asyncSetUp(self):
        self.client = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        await self.client.__aenter__()

    async def asyncTearDown(self):
        await self.client.close()

    async def use_application(self):
        await self.client.close()
        with patch.object(commands.Bot, "run"), patch("json.load", return_value={"preloaded": []}):
            if "bot" in sys.modules:
                application = importlib.reload(sys.modules["bot"])
            else:
                application = importlib.import_module("bot")
        self.client = application.client
        await self.client.__aenter__()
        return application

    async def load_cog(self, extension, name):
        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.load_extension(f"unity_cogs.{extension}")
        return sys.modules[f"unity_cogs.{extension}"], self.client.get_cog(name)

    async def invoke(self, cog, name, ctx, *args, **kwargs):
        command = getattr(cog, name)
        if isinstance(command, discord.app_commands.Command):
            module = sys.modules[cog.__module__]
            with patch.object(module, "command_context", AsyncMock(return_value=ctx)):
                return await command.callback(cog, Mock(spec=discord.Interaction), *args, **kwargs)
        return await command.callback(cog, ctx, *args, **kwargs)


class AsyncCursor:
    def __init__(self, documents):
        self.documents = documents

    def limit(self, count):
        return self

    def __aiter__(self):
        return self.iterate()

    async def iterate(self):
        for document in self.documents:
            yield document
