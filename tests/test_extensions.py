import asyncio
import importlib
import json
import os
import subprocess
import sys
import textwrap
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from discord.ext import commands

from tests.support import BotTestCase, TEST_ENV


class ExtensionTests(BotTestCase):
    async def test_extension_registers_its_cog_and_listener(self):
        await self.client.load_extension("unity_cogs.feedback")

        self.assertIsNotNone(self.client.get_cog("Feedback"))
        self.assertEqual(len(self.client.extra_events["on_message"]), 1)

    async def test_startup_preloads_configured_extensions(self):
        application = await self.use_application()
        application.conf["preloaded"] = ["feedback"]

        await self.client.setup_hook()

        self.assertIn("unity_cogs.feedback", self.client.extensions)
        self.assertIsNotNone(self.client.get_cog("Feedback"))

    async def test_failed_preload_logs_the_extension_and_stops_startup(self):
        application = await self.use_application()
        application.conf["preloaded"] = ["missing_extension", "feedback"]

        with self.assertLogs(level="ERROR") as logs:
            with self.assertRaises(commands.ExtensionNotFound):
                await self.client.setup_hook()

        self.assertIn("unity_cogs.missing_extension", "\n".join(logs.output))
        self.assertNotIn("unity_cogs.feedback", self.client.extensions)

    async def test_owner_load_registers_extension_before_announcing_success(self):
        application = await self.use_application()

        async def confirm_loaded(content):
            self.assertIsNotNone(self.client.get_cog("Feedback"))

        ctx = SimpleNamespace(send=AsyncMock(side_effect=confirm_loaded))
        await application.load.callback(ctx, "feedback")

        ctx.send.assert_awaited_once_with("feedback loaded")

    async def test_owner_unload_removes_extension_before_announcing_success(self):
        application = await self.use_application()
        await self.client.load_extension("unity_cogs.feedback")

        async def confirm_unloaded(content):
            self.assertIsNone(self.client.get_cog("Feedback"))
            self.assertNotIn("unity_cogs.feedback", self.client.extensions)

        ctx = SimpleNamespace(send=AsyncMock(side_effect=confirm_unloaded))
        await application.unload.callback(ctx, "feedback")

        ctx.send.assert_awaited_once_with("feedback unloaded")

    async def test_owner_reload_replaces_cog_before_announcing_success(self):
        application = await self.use_application()
        await self.client.load_extension("unity_cogs.feedback")
        original = self.client.get_cog("Feedback")

        async def confirm_reloaded(content):
            self.assertIsNotNone(self.client.get_cog("Feedback"))
            self.assertIsNot(self.client.get_cog("Feedback"), original)
            self.assertEqual(len(self.client.extra_events["on_message"]), 1)

        ctx = SimpleNamespace(send=AsyncMock(side_effect=confirm_reloaded))
        await application.reload.callback(ctx, "feedback")

        ctx.send.assert_awaited_once_with("feedback reloaded")

    async def test_failed_owner_load_reports_error_without_announcing_success(self):
        application = await self.use_application()
        ctx = SimpleNamespace(send=AsyncMock(), command=application.load)

        with self.assertRaises(commands.ExtensionNotFound) as failure:
            await application.load.callback(ctx, "missing_extension")
        ctx.send.assert_not_called()

        with self.assertLogs(level="ERROR") as logs:
            with patch.object(commands.Bot, "on_command_error", new_callable=AsyncMock):
                await self.client.on_command_error(ctx, commands.CommandInvokeError(failure.exception))

        ctx.send.assert_awaited_once()
        self.assertIn("missing_extension", ctx.send.call_args.args[0])
        self.assertIn("missing_extension", "\n".join(logs.output))
        self.assertNotIn("unity_cogs.missing_extension", self.client.extensions)

    async def test_application_requests_message_content_for_prefix_commands(self):
        await self.use_application()

        self.assertTrue(self.client.intents.message_content)
        self.assertTrue(self.client.intents.members)

    async def test_verification_monitor_waits_for_discord_readiness(self):
        ready = asyncio.Event()
        queried = asyncio.Event()

        async def count_documents(query):
            queried.set()
            return 0

        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            module = importlib.import_module("unity_cogs.verify")
        queue = SimpleNamespace(count_documents=AsyncMock(side_effect=count_documents))
        with patch.object(module, "db", SimpleNamespace(queue=queue)), patch.object(self.client, "wait_until_ready", ready.wait):
            cog = module.Verify(self.client)
            task = cog.monitor_db.get_task()
            try:
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                queue.count_documents.assert_not_awaited()

                ready.set()
                await asyncio.wait_for(queried.wait(), timeout=1)
                queue.count_documents.assert_awaited_once_with({})
            finally:
                cog.cog_unload()
                with suppress(asyncio.CancelledError):
                    await task
        self.assertTrue(task.cancelled())

    async def test_all_configured_extensions_register_their_commands(self):
        application = await self.use_application()
        application.conf = json.loads(Path("config.json").read_text())

        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.setup_hook()

        self.assertEqual(set(self.client.extensions), {
            f"unity_cogs.{name}" for name in application.conf["preloaded"]
        })
        self.assertEqual(set(self.client.cogs), {
            "Feedback", "Verify", "Cex", "Limiter", "Ebay", "Notes", "MOT",
            "UniversalScammerList", "EmbedRemover", "ReactReport",
        })
        self.assertEqual({command.qualified_name for command in self.client.walk_commands()}, {
            "help", "load", "unload", "reload", "verify", "whois", "editflair", "status",
            "removeuser", "search", "limiter", "limiter whitelist", "check", "notes",
            "notes view", "notes find", "notes delete", "notes create", "mot", "usl",
        })

    async def test_report_extension_loads_without_another_cog_importing_motor_first(self):
        script = textwrap.dedent('''
            import asyncio
            import logging
            from unittest.mock import patch
            import discord
            from discord.ext import commands

            async def check():
                async with commands.Bot(command_prefix="!", intents=discord.Intents.none()) as client:
                    await client.load_extension("unity_cogs.react_report")
                    assert client.get_cog("ReactReport") is not None

            with patch("logging.FileHandler", return_value=logging.NullHandler()), patch("logging.basicConfig"):
                asyncio.run(check())
        ''')

        result = await asyncio.to_thread(
            subprocess.run, [sys.executable, "-c", script], capture_output=True, text=True,
            env={**os.environ, **TEST_ENV}, timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    async def test_unloading_verification_cancels_its_background_monitor(self):
        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.load_extension("unity_cogs.verify")
        task = self.client.get_cog("Verify").monitor_db.get_task()
        await asyncio.sleep(0)

        await self.client.unload_extension("unity_cogs.verify")

        with suppress(asyncio.CancelledError):
            await task
        self.assertTrue(task.cancelled())
        self.assertIsNone(self.client.get_cog("Verify"))

    async def test_optional_meme_extension_preserves_its_command_and_alias(self):
        await self.client.load_extension("unity_cogs.rendermeme")

        self.assertIsNotNone(self.client.get_cog("RenderMeme"))
        self.assertIsNotNone(self.client.get_command("rd"))
        self.assertIs(self.client.get_command("rd"), self.client.get_command("wa"))
