import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from tests.support import AsyncCursor, BotTestCase


NOTE = {"user": "17", "content": "Trade resolved", "added_by": "42", "hash": "abc1234", "date_added": 1700000000}


class NotesTests(BotTestCase):
    async def test_database_delete_failure_reports_failure_without_success(self):
        self.collection.find_one.return_value = NOTE
        self.collection.delete_one.side_effect = RuntimeError("database offline")
        self.cog.client.wait_for = AsyncMock(return_value=(SimpleNamespace(emoji="✅"), self.ctx.author))
        with self.assertLogs(level="ERROR"):
            await self.invoke(self.cog, "delete", self.ctx, "abc1234")
        self.assertIn("Couldn't remove", self.ctx.send.call_args.args[0])

    async def test_confirmed_note_deletion_does_not_require_reaction_cleanup_permissions(self):
        self.collection.find_one.return_value = NOTE
        self.cog.client.wait_for = AsyncMock(return_value=(SimpleNamespace(emoji="✅"), self.ctx.author))
        self.message.clear_reactions.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "no manage messages")
        await self.invoke(self.cog, "delete", self.ctx, "abc1234")
        self.collection.delete_one.assert_awaited_once_with({"hash":"abc1234"})

    async def test_hash_generation_retries_a_collision(self):
        self.collection.find_one.side_effect = [NOTE, None]
        with patch.object(self.module.random, "choice", side_effect=list("abc1234xyz5678")):
            self.assertEqual(await self.cog.gen_hash(), "xyz5678")

    async def test_insert_failure_is_reported_without_success_message(self):
        self.cog.gen_hash = AsyncMock(return_value="abc1234")
        self.collection.insert_one.side_effect = RuntimeError("offline")
        with self.assertLogs(level="ERROR"):
            await self.invoke(self.cog, "create", self.ctx, SimpleNamespace(id=17), "Text")
        self.assertIn("Couldn't add", self.ctx.send.call_args.args[0])

    async def test_confirmation_accepts_only_the_requester_and_original_message(self):
        self.collection.find_one.return_value = NOTE
        async def confirm(event, timeout, check):
            reaction = SimpleNamespace(message=self.message, emoji="✅")
            self.assertFalse(check(reaction, SimpleNamespace(id=99)))
            self.assertFalse(check(SimpleNamespace(message=SimpleNamespace(id=999), emoji="✅"), self.ctx.author))
            self.assertTrue(check(reaction, self.ctx.author))
            return reaction, self.ctx.author
        self.cog.client.wait_for = AsyncMock(side_effect=confirm)
        await self.invoke(self.cog, "delete", self.ctx, "abc1234")
        self.collection.delete_one.assert_awaited_once_with({"hash":"abc1234"})

    async def test_timed_out_deletion_preserves_the_note(self):
        self.collection.find_one.return_value = NOTE
        self.cog.client.wait_for = AsyncMock(side_effect=asyncio.TimeoutError)
        await self.invoke(self.cog, "delete", self.ctx, "abc1234")
        self.collection.delete_one.assert_not_called()

    async def test_cancelled_deletion_preserves_the_note(self):
        self.collection.find_one.return_value = NOTE
        self.cog.client.wait_for = AsyncMock(return_value=(SimpleNamespace(emoji="❌"), self.ctx.author))
        await self.invoke(self.cog, "delete", self.ctx, "abc1234")
        self.collection.delete_one.assert_not_called()
        self.message.clear_reactions.assert_awaited_once()

    async def test_delete_missing_note_does_not_write(self):
        await self.invoke(self.cog, "delete", self.ctx, "abc1234")
        self.collection.delete_one.assert_not_called()

    async def test_delete_rejects_invalid_hash_without_writing(self):
        await self.invoke(self.cog, "delete", self.ctx, "bad")
        self.collection.find_one.assert_not_called()
        self.collection.delete_one.assert_not_called()

    async def test_long_note_display_stays_within_discord_embed_limits(self):
        embed = self.cog.make_note_embed({**NOTE, "content": "x" * 5000})
        self.assertLessEqual(len(embed.description), 4096)

    async def test_create_does_not_save_whitespace_only_content(self):
        self.cog.gen_hash = AsyncMock(return_value="abc1234")
        await self.invoke(self.cog, "create", self.ctx, SimpleNamespace(id=17), "   ")
        self.collection.insert_one.assert_not_called()
        self.assertIn("content", str(self.ctx.send.call_args).lower())

    async def test_create_saves_discord_ids_as_strings(self):
        self.cog.gen_hash = AsyncMock(return_value="abc1234")
        await self.invoke(self.cog, "create", self.ctx, SimpleNamespace(id=17), "Trade resolved")
        data = self.collection.insert_one.call_args.args[0]
        self.assertEqual((data["user"],data["added_by"],data["content"]), ("17","42","Trade resolved"))
        self.assertIn("Saved note successfully", self.ctx.send.call_args.kwargs["content"])

    async def test_find_missing_note_reports_no_results(self):
        await self.invoke(self.cog, "find", self.ctx, "abc1234")
        self.assertIn("No note found", self.ctx.send.call_args.kwargs["embed"].title)

    async def test_find_normalises_hash_case(self):
        self.collection.find_one.return_value = NOTE
        await self.invoke(self.cog, "find", self.ctx, "ABC1234")
        self.collection.find_one.assert_awaited_once_with({"hash":"abc1234"})
        self.assertIn("Trade resolved", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_find_rejects_invalid_hash_without_reading_the_database(self):
        await self.invoke(self.cog, "find", self.ctx, "bad")
        self.collection.find_one.assert_not_called()
        self.assertIn("valid note hash", self.ctx.send.call_args.kwargs["embed"].title)

    async def test_multiple_notes_are_paginated_newest_first(self):
        self.collection.count_documents.return_value = 2
        self.collection.find.return_value = AsyncCursor([NOTE, {**NOTE, "content":"New note"}])
        await self.invoke(self.cog, "view", self.ctx, SimpleNamespace(id=17))
        self.assertIn("New note", self.ctx.send.call_args.kwargs["embed"].description)
        self.addCleanup(self.ctx.send.call_args.kwargs["view"].stop)

    async def test_view_one_note_shows_content_and_author(self):
        self.collection.count_documents.return_value = 1
        self.collection.find.return_value = AsyncCursor([NOTE])
        await self.invoke(self.cog, "view", self.ctx, SimpleNamespace(id=17))
        embed = self.ctx.send.call_args.kwargs["embed"]
        self.assertIn("Trade resolved", embed.description)
        self.assertEqual(embed.fields[1].value, "<@42>")

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.module, self.cog = await self.load_cog("notes", "Notes")
        self.collection = SimpleNamespace(find_one=AsyncMock(return_value=None), insert_one=AsyncMock(),
            delete_one=AsyncMock(), count_documents=AsyncMock(return_value=0), find=Mock(return_value=AsyncCursor([])))
        self.enterContext(patch.object(self.module, "db", SimpleNamespace(notes=self.collection)))
        self.message = SimpleNamespace(id=123, add_reaction=AsyncMock(), clear_reactions=AsyncMock())
        self.ctx = SimpleNamespace(author=SimpleNamespace(id=42), send=AsyncMock(return_value=self.message),
                                   guild=SimpleNamespace(me=SimpleNamespace(colour=discord.Colour.blue())))

    async def test_view_without_notes_reports_no_results(self):
        await self.invoke(self.cog, "view", self.ctx, SimpleNamespace(id=17))
        self.assertIn("No notes", self.ctx.send.call_args.kwargs["embed"].description)
        self.collection.insert_one.assert_not_called()
