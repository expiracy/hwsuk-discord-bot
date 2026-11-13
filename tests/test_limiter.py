import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord

from tests.support import BotTestCase


class LimiterTests(BotTestCase):
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
