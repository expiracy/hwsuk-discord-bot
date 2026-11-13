import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from tests.support import BotTestCase


class LimiterTests(BotTestCase):
    async def test_non_positive_whitelist_duration_is_rejected(self):
        module, cog = await self.load_cog("limiter","Limiter")
        member = SimpleNamespace(id=42, mention="<@42>", colour=discord.Colour.blue())
        ctx = SimpleNamespace(send=AsyncMock())
        with patch.object(module.asyncio, "sleep", AsyncMock()) as sleep:
            await self.invoke(cog, "whitelist", ctx, member, -1)
            sleep.assert_not_called()
        self.assertIn("positive", str(ctx.send.call_args).lower())

    async def test_cancellation_does_not_leave_a_permanent_whitelist_entry(self):
        import asyncio
        module, cog = await self.load_cog("limiter","Limiter")
        member = SimpleNamespace(id=42, mention="<@42>", colour=discord.Colour.blue())
        with patch.object(module.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await self.invoke(cog, "whitelist", SimpleNamespace(send=AsyncMock()), member, 10)
        self.assertNotIn(42, cog.whitelisted_users)

    async def test_whitelist_expires_after_the_requested_duration(self):
        module, cog = await self.load_cog("limiter","Limiter")
        member = SimpleNamespace(id=42, mention="<@42>", colour=discord.Colour.blue())
        async def duration(seconds):
            self.assertEqual(seconds, 10)
            self.assertIn(42, cog.whitelisted_users)
        with patch.object(module.asyncio, "sleep", AsyncMock(side_effect=duration)):
            await self.invoke(cog, "whitelist", SimpleNamespace(send=AsyncMock()), member, 10)
        self.assertNotIn(42, cog.whitelisted_users)

    async def test_http_deletion_failure_is_logged_without_a_success_notice(self):
        cog, message = await self.duplicate_with_error(discord.HTTPException(SimpleNamespace(status=500, reason="Server Error"), "failed"))
        with self.assertLogs(level="ERROR"):
            await cog.on_message(message)
        cog.send_info_message.assert_not_called()

    async def test_already_deleted_post_does_not_send_another_notice(self):
        cog, message = await self.duplicate_with_error(discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "gone"))
        await cog.on_message(message)
        cog.send_info_message.assert_not_called()

    async def test_forbidden_deletion_never_claims_the_post_was_removed(self):
        cog, message = await self.duplicate_with_error(discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "denied"))
        with self.assertLogs(level="WARNING"):
            await cog.on_message(message)
        cog.send_info_message.assert_not_called()

    async def duplicate_with_error(self, error):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        cog.client = SimpleNamespace(user=SimpleNamespace(id=999))
        cog.send_info_message = AsyncMock()
        author = SimpleNamespace(id=42, bot=False)
        async def history():
            yield SimpleNamespace(id=10, author=author, created_at=discord.utils.utcnow())
        message = SimpleNamespace(id=11, author=author, content="Post", delete=AsyncMock(side_effect=error),
            channel=SimpleNamespace(id=4, history=Mock(return_value=history())))
        return cog, message

    async def test_a_duplicate_stops_history_reads_and_is_deleted_only_once(self):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        cog.client = SimpleNamespace(user=SimpleNamespace(id=999))
        cog.send_info_message = AsyncMock()
        author = SimpleNamespace(id=42, bot=False)
        async def history():
            yield SimpleNamespace(id=10, author=author, created_at=discord.utils.utcnow())
            self.fail("History should stop after finding a duplicate")
        message = SimpleNamespace(id=11, author=author, content="Post", delete=AsyncMock(),
            channel=SimpleNamespace(id=4, history=Mock(return_value=history())))
        await cog.on_message(message)
        message.delete.assert_awaited_once()
        cog.send_info_message.assert_awaited_once()

    async def test_failed_dm_send_falls_back_to_backup(self):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        output = SimpleNamespace(send=AsyncMock())
        cog.client = SimpleNamespace(get_channel=Mock(return_value=output))
        cog.make_embed = AsyncMock(return_value=discord.Embed(description="Post"))
        author = SimpleNamespace(id=42, dm_channel=SimpleNamespace(send=AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "closed"))))
        await cog.send_info_message(author, 4, "Post", discord.utils.utcnow())
        output.send.assert_awaited_once()

    async def test_closed_dm_creation_falls_back_to_the_backup_channel(self):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        output = SimpleNamespace(send=AsyncMock())
        cog.client = SimpleNamespace(get_channel=Mock(return_value=output))
        cog.make_embed = AsyncMock(return_value=discord.Embed(description="Post"))
        author = SimpleNamespace(id=42, dm_channel=None, create_dm=AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "closed")))
        await cog.send_info_message(author, 4, "Post", discord.utils.utcnow())
        output.send.assert_awaited_once()
        self.assertIn("<@42>", output.send.call_args.kwargs["content"])
        allowed = output.send.call_args.kwargs.get("allowed_mentions")
        self.assertIsNotNone(allowed)
        self.assertEqual(allowed.to_dict(), {"parse": [], "users": [42]})

    async def test_whitelisted_users_do_not_query_history(self):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        cog.client = SimpleNamespace(user=SimpleNamespace(id=999))
        cog.whitelisted_users.append(42)
        channel = SimpleNamespace(id=4, history=Mock())
        await cog.on_message(SimpleNamespace(author=SimpleNamespace(id=42, bot=False), channel=channel))
        channel.history.assert_not_called()

    async def test_bot_messages_are_ignored(self):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        cog.client = SimpleNamespace(user=SimpleNamespace(id=999))
        message = SimpleNamespace(author=SimpleNamespace(id=42, bot=True))
        await cog.on_message(message)

    async def test_history_query_covers_the_whole_cooldown_window(self):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        cog.client = SimpleNamespace(user=SimpleNamespace(id=999))
        async def history():
            for item in []:
                yield item
        channel = SimpleNamespace(id=4, history=Mock(return_value=history()))
        message = SimpleNamespace(author=SimpleNamespace(id=42, bot=False), channel=channel, content="Post")
        await cog.on_message(message)
        self.assertIsNone(channel.history.call_args.kwargs.get("limit", "default cap"))

    async def test_duplicate_post_is_removed_using_async_history(self):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        cog.client = SimpleNamespace(user=SimpleNamespace(id=999))
        cog.send_info_message = AsyncMock()
        author = SimpleNamespace(id=42, bot=False)
        previous = SimpleNamespace(author=author, id=10, created_at=discord.utils.utcnow())

        async def history():
            yield previous

        channel = SimpleNamespace(id=4, history=Mock(return_value=history()))
        message = SimpleNamespace(id=11, author=author, channel=channel, content="For sale", delete=AsyncMock())

        await cog.on_message(message)

        message.delete.assert_awaited_once_with()
        cog.send_info_message.assert_awaited_once_with(author, 4, "For sale", previous.created_at)

    async def test_history_cutoff_uses_utc_instead_of_the_hosts_local_time(self):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        cog.client = SimpleNamespace(user=SimpleNamespace(id=999))

        async def history():
            return
            yield

        channel = SimpleNamespace(id=4, history=Mock(return_value=history()))
        message = SimpleNamespace(author=SimpleNamespace(id=42, bot=False), channel=channel, content="For sale")
        before = discord.utils.utcnow() - datetime.timedelta(days=3)

        await cog.on_message(message)

        cutoff = channel.history.call_args.kwargs["after"]
        self.assertEqual(cutoff.tzinfo, datetime.timezone.utc)
        self.assertGreaterEqual(cutoff, before)
        self.assertLessEqual(cutoff, discord.utils.utcnow() - datetime.timedelta(days=3))

    async def test_deleted_post_embed_uses_the_members_display_avatar(self):
        await self.client.load_extension("unity_cogs.limiter")
        cog = self.client.get_cog("Limiter")
        cog.client = SimpleNamespace(fetch_user=AsyncMock(return_value=SimpleNamespace(discriminator="0")))
        author = SimpleNamespace(
            id=42, display_name="Seller", colour=discord.Colour.blue(), avatar=None,
            display_avatar=SimpleNamespace(url="https://cdn.discordapp.com/embed/avatars/5.png"),
        )

        embed = await cog.make_embed(author, "For sale")

        self.assertEqual(embed.author.icon_url, author.display_avatar.url)
        self.assertEqual(embed.author.name, "Seller")
        self.assertEqual(embed.description, "For sale")
        cog.client.fetch_user.assert_not_called()
