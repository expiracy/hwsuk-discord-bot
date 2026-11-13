import runpy
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
from discord.ext import commands

from tests.slash_support import SlashBotTestCase


class DiscordPracticeTests(SlashBotTestCase):
    async def test_container_heartbeat_tracks_disconnect_resume_and_shutdown(self):
        application = await self.use_application()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            with patch.object(application.bot_config, "BOT_HEALTH_FILE", str(path)):
                await application.on_resumed()
                await self.client.heartbeat()
                self.assertTrue(application.health.is_healthy(path))
                await application.on_disconnect()
                await self.client.heartbeat()
                self.assertFalse(application.health.is_healthy(path))
                await self.client.close()
                self.assertFalse(path.exists())

    async def test_stdout_only_startup_does_not_create_or_open_log_files(self):
        with patch("unity_util.bot_config.LOGGING_FILENAME", ""), patch.object(commands.Bot, "run"), patch("pathlib.Path.mkdir") as mkdir:
            with patch("logging.FileHandler") as file_handler:
                runpy.run_path("bot.py", run_name="__main__")
        mkdir.assert_not_called()
        file_handler.assert_not_called()

    async def test_entrypoint_creates_logs_and_starts_with_environment_token(self):
        with patch.object(commands.Bot, "run") as start, patch("pathlib.Path.mkdir") as mkdir:
            runpy.run_path("bot.py", run_name="__main__")
        mkdir.assert_called_once_with(exist_ok=True)
        start.assert_called_once_with("test-token", log_handler=None)

    async def test_component_cleanup_tolerates_an_already_deleted_message(self):
        from unity_util.menus import menu
        ctx = SimpleNamespace(author=SimpleNamespace(id=42), send=AsyncMock())
        await menu(ctx, [discord.Embed(title="One"),discord.Embed(title="Two")])
        view = ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)
        view.message.edit.side_effect = discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "deleted")
        await view.on_timeout()
        self.assertTrue(all(item.disabled for item in view.children))

    async def test_unexpected_command_errors_are_private_and_do_not_leak_internal_details(self):
        application = await self.use_application()
        command = self.client.tree.get_command("help")
        interaction = self.interaction(command)
        error = discord.app_commands.CommandInvokeError(command, RuntimeError("private credentials"))
        with self.assertLogs(level="ERROR"):
            await application.on_app_command_error(interaction, error)
        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])
        self.assertNotIn("private credentials", interaction.response.send_message.call_args.args[0])

    async def test_unneeded_presence_typing_and_voice_events_are_disabled(self):
        await self.use_application()
        self.assertFalse(self.client.intents.presences)
        self.assertFalse(self.client.intents.typing)
        self.assertFalse(self.client.intents.voice_states)

    async def test_replayed_user_content_cannot_trigger_mass_or_user_mentions(self):
        await self.use_application()
        self.assertIsNotNone(self.client.allowed_mentions)
        self.assertEqual(self.client.allowed_mentions.to_dict(), {"parse": []})
