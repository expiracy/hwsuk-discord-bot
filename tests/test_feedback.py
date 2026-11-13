import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord

from tests.support import BotTestCase


class FeedbackTests(BotTestCase):
    async def test_failed_moderator_delivery_can_be_retried(self):
        self.output.send.side_effect = [discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "denied"), None]
        await self.cog.on_raw_reaction_add(self.payload)
        await self.cog.on_raw_reaction_add(self.payload)
        self.assertEqual(self.output.send.await_count, 2)

    async def test_votes_after_the_24_hour_window_do_not_notify(self):
        self.message.created_at -= timedelta(days=2)
        await self.cog.on_raw_reaction_add(self.payload)
        self.output.send.assert_not_called()

    async def test_normal_feedback_receives_both_vote_reactions(self):
        await self.cog.on_message(self.message)
        self.assertEqual([call.args[0] for call in self.message.add_reaction.await_args_list], ["👍", "👎"])

    async def test_long_feedback_fits_discord_field_limits(self):
        self.message.content = "x" * 2000
        await self.cog.on_raw_reaction_add(self.payload)
        embed = self.output.send.call_args.kwargs["embed"]
        self.assertLessEqual(len(embed.fields[0].value), 1024)
        self.assertIn("/123", embed.author.url)

    async def test_deleted_feedback_is_ignored(self):
        self.channel.fetch_message.side_effect = discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "deleted")
        await self.cog.on_raw_reaction_add(self.payload)
        self.output.send.assert_not_called()

    async def test_concurrent_threshold_events_notify_only_once(self):
        await asyncio.gather(self.cog.on_raw_reaction_add(self.payload), self.cog.on_raw_reaction_add(self.payload))
        self.output.send.assert_awaited_once()

    async def test_below_threshold_does_not_notify(self):
        self.message.reactions[0].count = 3
        await self.cog.on_raw_reaction_add(self.payload)
        self.output.send.assert_not_called()

    async def test_bot_reactions_do_not_notify(self):
        self.payload.member.bot = True
        await self.cog.on_raw_reaction_add(self.payload)
        self.channel.fetch_message.assert_not_called()

    async def test_unrelated_channel_does_not_fetch_or_notify(self):
        self.payload.channel_id = 9
        await self.cog.on_raw_reaction_add(self.payload)
        self.channel.fetch_message.assert_not_called()
        self.output.send.assert_not_called()

    async def test_raw_reaction_on_an_uncached_message_notifies_moderators(self):
        await self.cog.on_raw_reaction_add(self.payload)

        self.channel.fetch_message.assert_awaited_once_with(123)
        self.output.send.assert_awaited_once()
        self.assertEqual(self.output.send.call_args.kwargs["embed"].fields[0].value, "A suggestion")

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.module, self.cog = await self.load_cog("feedback", "Feedback")
        self.output = SimpleNamespace(send=AsyncMock())
        self.message = SimpleNamespace(
            id=123, channel=SimpleNamespace(id=2), author=SimpleNamespace(id=42, bot=False),
            guild=SimpleNamespace(id=1), content="A suggestion", created_at=discord.utils.utcnow(),
            reactions=[SimpleNamespace(emoji="👍", count=4, me=True)], add_reaction=AsyncMock(),
        )
        self.channel = SimpleNamespace(fetch_message=AsyncMock(return_value=self.message))
        self.cog.client = SimpleNamespace(
            user=SimpleNamespace(id=999),
            get_channel=Mock(side_effect=lambda channel: {2: self.channel, 3: self.output}.get(channel)),
            wait_for=AsyncMock(side_effect=asyncio.TimeoutError),
        )
        self.payload = SimpleNamespace(guild_id=1, channel_id=2, message_id=123, user_id=42,
                                       emoji=SimpleNamespace(name="👍"), member=SimpleNamespace(bot=False))

    async def test_other_bots_do_not_start_feedback_votes(self):
        self.message.author.bot = True

        await self.cog.on_message(self.message)

        self.message.add_reaction.assert_not_called()
