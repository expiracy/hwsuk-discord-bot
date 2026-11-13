import importlib
import logging
import os
import sys
import unittest
from unittest.mock import patch

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
