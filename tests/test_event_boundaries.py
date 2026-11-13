from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from tests.support import BotTestCase


class EventBoundaryTests(BotTestCase):
    async def test_meme_command_sends_one_of_the_configured_links(self):
        module, cog = await self.load_cog("rendermeme", "RenderMeme")
        ctx = SimpleNamespace(send=AsyncMock())
        await self.invoke(cog, "_rd", ctx)
        self.assertIn(ctx.send.call_args.kwargs["content"], module.IMAGE_LINKS)

    async def test_configured_cogs_ready_callbacks_do_not_raise(self):
        for name, cls in [("cex","Cex"),("embedremover","EmbedRemover"),("feedback","Feedback"),("limiter","Limiter"),("mot","MOT"),("notes","Notes"),("react_report","ReactReport"),("rendermeme","RenderMeme"),("usl","UniversalScammerList")]:
            _, cog = await self.load_cog(name, cls)
            await cog.on_ready()

    async def test_embed_remover_handles_permission_denial(self):
        _, cog = await self.load_cog("embedremover", "EmbedRemover")
        message = SimpleNamespace(id=123, author="Tester", channel=SimpleNamespace(id=5), edit=AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "denied")))
        with self.assertLogs(level="WARNING"):
            await cog.on_message(message)

    async def test_embed_remover_ignores_other_channels(self):
        _, cog = await self.load_cog("embedremover", "EmbedRemover")
        message = SimpleNamespace(channel=SimpleNamespace(id=9), edit=AsyncMock())
        await cog.on_message(message)
        message.edit.assert_not_called()

    async def test_embed_removal_only_edits_the_configured_channel(self):
        _, cog = await self.load_cog("embedremover", "EmbedRemover")
        message = SimpleNamespace(id=123, author="Tester", channel=SimpleNamespace(id=5), edit=AsyncMock())
        await cog.on_message(message)
        message.edit.assert_awaited_once_with(suppress=True)
