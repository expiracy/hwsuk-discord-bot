import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
from pymongo.errors import DuplicateKeyError

from tests.support import BotTestCase


class ReportTests(BotTestCase):
    async def test_raw_dm_deletion_is_ignored(self):
        self.payload.guild_id = None
        await self.cog.on_raw_message_delete(self.payload)
        self.collection.find_one_and_delete.assert_not_called()

    async def test_retraction_with_missing_source_guild_is_ignored(self):
        self.cog.client.get_guild.return_value = None
        await self.cog.on_raw_reaction_remove(self.payload)
        self.collection.find_one_and_delete.assert_not_called()

    async def test_missing_source_message_is_ignored(self):
        self.channel.fetch_message.return_value = None
        await self.cog.on_raw_reaction_add(self.payload)
        self.collection.update_one.assert_not_called()

    async def test_existing_upsert_does_not_notify_again(self):
        self.collection.update_one.return_value = SimpleNamespace(upserted_id=None)
        await self.cog.on_raw_reaction_add(self.payload)
        self.output.send.assert_not_called()

    async def test_cached_and_raw_deletion_do_not_double_notify(self):
        self.collection.find_one_and_delete.side_effect = [{"message_id":123, "message_content":"Text"}, None]
        await self.cog.on_message_delete(self.message)
        await self.cog.on_raw_message_delete(self.payload)
        self.output.send.assert_awaited_once()

    async def test_last_warning_removal_notifies_once_for_existing_report(self):
        self.collection.find_one_and_delete.return_value = {"message_id":123}
        self.message.reactions = [SimpleNamespace(emoji="👍", count=1)]
        await self.cog.on_raw_reaction_remove(self.payload)
        self.assertEqual(self.output.send.call_args.kwargs["embed"].title, "Report retracted")

    async def test_missing_output_channel_does_not_save_a_report(self):
        self.guild.get_channel.side_effect = lambda i: self.channel if i == 2 else None
        await self.cog.on_raw_reaction_add(self.payload)
        self.collection.update_one.assert_not_called()

    async def test_missing_source_channel_is_ignored(self):
        self.guild.get_channel.side_effect = lambda i: self.output if i == 6 else None
        await self.cog.on_raw_reaction_add(self.payload)
        self.output.send.assert_not_called()

    async def test_non_report_emoji_is_ignored(self):
        self.payload.emoji.name = "👍"
        await self.cog.on_raw_reaction_add(self.payload)
        await self.cog.on_raw_reaction_remove(self.payload)
        self.channel.fetch_message.assert_not_called()

    async def test_dm_reactions_are_ignored(self):
        self.payload.guild_id = None
        await self.cog.on_raw_reaction_add(self.payload)
        await self.cog.on_raw_reaction_remove(self.payload)
        self.collection.update_one.assert_not_called()

    async def test_uncached_message_deletion_notifies_using_stored_report(self):
        self.collection.find_one_and_delete.return_value = {"message_id": 123, "message_content": "Stored text"}
        await self.cog.on_raw_message_delete(self.payload)
        self.output.send.assert_awaited_once()
        self.assertEqual(self.output.send.call_args.kwargs["embed"].description, "Stored text")

    async def test_report_removal_returns_the_deleted_document_atomically(self):
        document = {"message_id": 123, "message_content": "Text"}
        self.collection.find_one_and_delete.return_value = document
        self.assertEqual(await self.cog.remove_report_data(123), document)
        self.collection.find_one_and_delete.assert_awaited_once_with({"message_id": 123})

    async def test_atomic_duplicate_does_not_send_another_notification(self):
        self.collection.update_one.side_effect = DuplicateKeyError("already reported")
        await self.cog.on_raw_reaction_add(self.payload)
        self.output.send.assert_not_called()

    async def test_duplicate_report_creation_uses_an_atomic_upsert(self):
        self.assertTrue(await self.cog.save_report_data({"message_id": 123, "message_content": "Text"}))
        self.collection.update_one.assert_awaited_once_with(
            {"message_id": 123},
            {"$setOnInsert": {"_id": 123, "message_id": 123, "message_content": "Text"}}, upsert=True)
        self.collection.insert_one.assert_not_called()

    async def test_last_warning_retraction_only_notifies_for_an_existing_report(self):
        self.collection.count_documents.return_value = 0
        await self.cog.on_raw_reaction_remove(self.payload)
        self.output.send.assert_not_called()

    async def test_dm_deletion_does_not_touch_reports(self):
        await self.cog.on_message_delete(SimpleNamespace(guild=None, id=123))
        self.collection.delete_one.assert_not_called()
        self.collection.find_one_and_delete.assert_not_called()

    async def test_report_does_not_require_reporter_to_be_cached(self):
        self.guild.get_member.return_value = None
        await self.cog.on_raw_reaction_add(self.payload)
        self.assertEqual(self.output.send.call_args.kwargs["embed"].fields[0].value, "<@42>")

    async def test_report_for_deleted_message_is_ignored(self):
        self.channel.fetch_message.side_effect = discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "gone")
        await self.cog.on_raw_reaction_add(self.payload)
        self.output.send.assert_not_called()

    async def test_missing_guild_is_ignored(self):
        self.cog.client.get_guild.return_value = None
        await self.cog.on_raw_reaction_add(self.payload)
        self.output.send.assert_not_called()

    async def test_unicode_warning_still_present_does_not_retract_report(self):
        self.message.reactions = [SimpleNamespace(emoji="⚠️", count=1)]
        await self.cog.on_raw_reaction_remove(self.payload)
        self.collection.delete_one.assert_not_called()
        self.collection.find_one_and_delete.assert_not_called()
        self.output.send.assert_not_called()

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.module, self.cog = await self.load_cog("react_report", "ReactReport")
        self.collection = SimpleNamespace(count_documents=AsyncMock(return_value=0),
            insert_one=AsyncMock(), delete_one=AsyncMock(), find_one_and_delete=AsyncMock(return_value=None),
            update_one=AsyncMock(return_value=SimpleNamespace(upserted_id=123)))
        self.enterContext(patch.object(self.module, "db", SimpleNamespace(reports=self.collection)))
        self.output = SimpleNamespace(send=AsyncMock())
        self.channel = SimpleNamespace(id=2, fetch_message=AsyncMock())
        self.guild = SimpleNamespace(id=1, get_channel=Mock(side_effect=lambda i: {2:self.channel,6:self.output}.get(i)),
                                     get_member=Mock(return_value=SimpleNamespace(mention="<@42>")))
        self.message = SimpleNamespace(id=123, guild=self.guild, clean_content="Please review", reactions=[],
                                       jump_url="https://discord.com/channels/1/2/123")
        self.channel.fetch_message.return_value = self.message
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=self.guild), user=SimpleNamespace(id=999))
        self.payload = SimpleNamespace(guild_id=1, channel_id=2, message_id=123, user_id=42,
                                       emoji=SimpleNamespace(name="⚠️"))

    async def test_report_timestamp_records_current_utc_time(self):
        before = discord.utils.utcnow()
        self.cog.save_report_data = AsyncMock(return_value=True)

        await self.cog.on_raw_reaction_add(self.payload)

        data = self.cog.save_report_data.call_args.args[0]
        self.assertEqual(data["report_timestamp"].tzinfo, before.tzinfo)
        self.assertGreaterEqual(data["report_timestamp"], before)
        self.output.send.assert_awaited_once()
