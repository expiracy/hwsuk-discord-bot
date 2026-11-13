import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from tests.support import AsyncCursor, BotTestCase


class VerificationTests(BotTestCase):
    async def test_trade_assignment_for_a_departed_member_returns_failure(self):
        guild = SimpleNamespace(get_role=Mock(return_value=SimpleNamespace(id=1)), get_member=Mock(return_value=None))
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=guild))
        self.assertFalse(await self.cog.set_trade_role(self.user_data, "3+"))

    async def test_missing_trade_role_does_not_attempt_assignment(self):
        member = SimpleNamespace(name="Tester", discriminator="0", add_roles=AsyncMock())
        guild = SimpleNamespace(name="Test", get_role=Mock(return_value=None), get_member=Mock(return_value=member))
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=guild))
        self.assertFalse(await self.cog.set_trade_role(self.user_data, "3+"))
        member.add_roles.assert_not_called()

    async def test_unban_in_another_guild_does_not_change_verification(self):
        self.users.find_one_and_update = AsyncMock()
        await self.cog.on_member_unban(SimpleNamespace(id=999, name="Other"), SimpleNamespace(id=42, name="User", discriminator="0"))
        self.users.find_one_and_update.assert_not_called()

    async def test_successful_flair_assignment_keeps_the_new_role_during_cleanup(self):
        self.ctx.author.roles = [SimpleNamespace(id=100)]
        self.cog.get_user = AsyncMock(return_value=self.user_data)
        self.cog.set_trade_flair = AsyncMock(return_value=True)
        self.cog.set_trade_role = AsyncMock(return_value=True)
        self.cog.remove_trades = AsyncMock()
        await self.invoke(self.cog, "editflair", self.ctx, "tester", "3+")
        self.cog.remove_trades.assert_awaited_once_with(self.user_data["discord"]["id"], keep_role=int(self.module.conf["flairs"]["3+"]["rid"]))
        self.assertIn("Role set successfully", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_username_falls_back_to_discord_after_reddit_misses(self):
        self.users.find_one.side_effect = [None, self.user_data]
        self.assertEqual(await self.cog.get_user("tester"), self.user_data)
        self.assertEqual(self.users.find_one.await_count, 2)

    async def test_legacy_discriminator_lookup_is_supported(self):
        self.users.find_one.return_value = self.user_data
        await self.cog.get_user("tester#1234")
        self.assertEqual(next(iter(self.users.find_one.call_args.args[0])), "discord.name")

    async def test_reddit_username_prefix_is_supported(self):
        self.users.find_one.return_value = self.user_data
        self.assertEqual(await self.cog.get_user("/u/redditor"), self.user_data)
        self.assertEqual(next(iter(self.users.find_one.call_args.args[0])), "reddit.name")

    async def test_role_api_failure_returns_false(self):
        member = SimpleNamespace(name="Tester", discriminator="0", add_roles=AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "denied")))
        guild = SimpleNamespace(name="Test", get_role=Mock(return_value=SimpleNamespace(id=1)), get_member=Mock(return_value=member))
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=guild))
        with self.assertLogs(level="ERROR"):
            self.assertFalse(await self.cog.set_trade_role(self.user_data, "3+"))

    async def test_reddit_flair_failure_returns_false(self):
        self.module.reddit.subreddit.return_value.flair.set.side_effect = RuntimeError("Reddit offline")
        with self.assertLogs(level="ERROR"):
            self.assertFalse(await self.cog.set_trade_flair(self.user_data, "3+"))

    async def test_whois_embed_includes_trade_role_and_unknown_usl_status(self):
        self.cog.get_trades = AsyncMock(return_value="3+")
        embed = await self.cog.make_whois_embed(self.user_data)
        fields = {f.name:f.value for f in embed.fields}
        self.assertEqual(fields["Trades"], "3+")
        self.assertIn("Unknown", fields["On USL"])

    async def test_unverified_rejoining_member_receives_no_role(self):
        self.users.find_one.return_value = None
        self.cog.set_verified = AsyncMock()
        await self.cog.on_member_join(SimpleNamespace(id=42))
        self.cog.set_verified.assert_not_called()

    async def test_rejoining_verified_member_receives_verification(self):
        self.users.find_one.return_value = {"verified":True}
        self.cog.set_verified = AsyncMock(return_value=True)
        await self.cog.on_member_join(SimpleNamespace(id=42))
        self.cog.set_verified.assert_awaited_once_with(42)

    async def test_ban_in_another_guild_does_not_change_this_servers_verification(self):
        self.users.find_one_and_update = AsyncMock()
        await self.cog.on_member_ban(SimpleNamespace(id=999), SimpleNamespace(id=42))
        self.users.find_one_and_update.assert_not_called()

    async def test_concurrent_queue_processors_do_not_verify_the_same_item_twice(self):
        pending = ["queued"]
        self.queue.count_documents.side_effect = lambda query: len(pending)
        self.queue.find.side_effect = lambda: AsyncCursor([{"_id":"queued", "ref":"user"}] if pending else [])
        self.queue.find_one_and_delete.side_effect = lambda query: pending.clear()
        async def verify(user_id):
            await asyncio.sleep(0)
            return True
        self.cog.set_verified = AsyncMock(side_effect=verify)
        await asyncio.gather(self.cog.monitor_db(), self.cog.monitor_db())
        self.cog.set_verified.assert_awaited_once()

    async def test_failed_discord_role_removal_does_not_delete_verification_record(self):
        self.ctx.author.roles = [SimpleNamespace(id=100)]
        self.cog.get_user = AsyncMock(return_value=self.user_data)
        self.cog.make_whois_embed = AsyncMock(return_value=discord.Embed(title="User"))
        self.cog.client.wait_for = AsyncMock(return_value=(SimpleNamespace(emoji="✅"), self.ctx.author))
        member = SimpleNamespace(remove_roles=AsyncMock(side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "hierarchy")))
        guild = SimpleNamespace(get_member=Mock(return_value=member), get_role=Mock(return_value=SimpleNamespace(id=101)))
        with patch.object(self.cog.client, "get_guild", return_value=guild):
            with self.assertLogs(level="ERROR"):
                await self.invoke(self.cog, "remove_user", self.ctx, "tester")
        self.users.delete_one.assert_not_called()

    async def test_removeuser_cancellation_preserves_database_record(self):
        self.ctx.author.roles = [SimpleNamespace(id=100)]
        self.cog.get_user = AsyncMock(return_value=self.user_data)
        self.cog.make_whois_embed = AsyncMock(return_value=discord.Embed(title="User"))
        self.cog.client.wait_for = AsyncMock(return_value=(SimpleNamespace(emoji="❌"), self.ctx.author))
        await self.invoke(self.cog, "remove_user", self.ctx, "tester")
        self.users.delete_one.assert_not_called()

    async def test_removeuser_timeout_preserves_database_record(self):
        self.ctx.author.roles = [SimpleNamespace(id=100)]
        self.cog.get_user = AsyncMock(return_value=self.user_data)
        self.cog.make_whois_embed = AsyncMock(return_value=discord.Embed(title="User"))
        self.cog.client.wait_for = AsyncMock(side_effect=asyncio.TimeoutError)
        await self.invoke(self.cog, "remove_user", self.ctx, "tester")
        self.users.delete_one.assert_not_called()

    async def test_removeuser_for_missing_record_does_not_delete(self):
        self.ctx.author.roles = [SimpleNamespace(id=100)]
        self.cog.get_user = AsyncMock(return_value={})
        await self.invoke(self.cog, "remove_user", self.ctx, "tester")
        self.users.delete_one.assert_not_called()

    async def test_removeuser_without_updater_role_does_not_read_or_delete_data(self):
        await self.invoke(self.cog, "remove_user", self.ctx, "tester")
        self.users.find_one.assert_not_called()
        self.users.delete_one.assert_not_called()

    async def test_failed_new_role_assignment_preserves_existing_trade_roles(self):
        self.ctx.author.roles = [SimpleNamespace(id=100)]
        self.cog.get_user = AsyncMock(return_value=self.user_data)
        self.cog.remove_trades = AsyncMock()
        self.cog.set_trade_flair = AsyncMock(return_value=True)
        self.cog.set_trade_role = AsyncMock(return_value=False)
        await self.invoke(self.cog, "editflair", self.ctx, "tester", "3+")
        self.cog.remove_trades.assert_not_called()
        self.assertIn("Error setting trade role", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_invalid_trade_flair_does_not_modify_roles(self):
        self.ctx.author.roles = [SimpleNamespace(id=100)]
        self.cog.get_user = AsyncMock(return_value=self.user_data)
        self.cog.remove_trades = AsyncMock()
        await self.invoke(self.cog, "editflair", self.ctx, "tester", "invalid")
        self.cog.remove_trades.assert_not_called()

    async def test_editflair_for_missing_user_reports_no_results(self):
        self.ctx.author.roles = [SimpleNamespace(id=100)]
        self.cog.get_user = AsyncMock(return_value={})
        await self.invoke(self.cog, "editflair", self.ctx, "tester", "3+")
        self.assertIn("No results", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_editflair_without_updater_role_never_modifies_data(self):
        self.cog.set_trade_role = AsyncMock()
        await self.invoke(self.cog, "editflair", self.ctx, "tester", "3+")
        self.cog.set_trade_role.assert_not_called()
        self.users.find_one.assert_not_called()

    async def test_status_with_record_reports_verified_flag(self):
        self.cog.get_user = AsyncMock(return_value=self.user_data)
        await self.invoke(self.cog, "status", self.ctx)
        fields = {f.name:f.value for f in self.ctx.send.call_args.kwargs["embed"].fields}
        self.assertEqual(fields["Verified"], "True")

    async def test_status_without_record_links_to_verification(self):
        self.cog.get_user = AsyncMock(return_value={})
        await self.invoke(self.cog, "status", self.ctx)
        self.assertIn("verify.hardwareswap.uk", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_whois_missing_user_reports_no_results(self):
        self.cog.get_user = AsyncMock(return_value={})
        await self.invoke(self.cog, "whois", self.ctx, "missing")
        self.assertIn("No results", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_reddit_flair_update_runs_off_the_event_loop_thread(self):
        event_loop_thread = threading.get_ident()
        seen = []
        self.module.reddit.subreddit.return_value.flair.set.side_effect = lambda *a, **k: seen.append(threading.get_ident())
        self.assertTrue(await self.cog.set_trade_flair({"reddit": {"name": "tester"}}, "3+"))
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(seen[0], event_loop_thread)

    async def test_unban_uses_atomic_update_and_string_discord_id(self):
        self.users.find_one_and_update = AsyncMock()
        await self.cog.on_member_unban(SimpleNamespace(name="Test", id=1), SimpleNamespace(id=42, name="Tester", discriminator="0"))
        self.users.find_one_and_update.assert_awaited_once_with({"discord.id": "42"}, {"$set": {"banned": False}})

    async def test_ban_event_uses_guild_user_signature_and_atomic_update(self):
        self.users.find_one_and_update = AsyncMock()
        await self.cog.on_member_ban(SimpleNamespace(name="Test", id=1), SimpleNamespace(id=42, name="Tester", discriminator="0"))
        self.users.find_one_and_update.assert_awaited_once_with({"discord.id": "42"}, {"$set": {"verified": False, "banned": True}})

    async def test_username_regex_metacharacters_are_matched_literally(self):
        self.users.find_one.return_value = None
        await self.cog.get_user(".*")
        queries = [c.args[0] for c in self.users.find_one.call_args_list]
        self.assertTrue(all(next(iter(q.values()))["$regex"] == r"^\.\*$" for q in queries))

    async def test_trade_removal_only_removes_configured_trade_roles(self):
        trade, other = SimpleNamespace(id=1), SimpleNamespace(id=9)
        member = SimpleNamespace(roles=[trade, other], remove_roles=AsyncMock())
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=SimpleNamespace(get_member=Mock(return_value=member))))
        with patch.object(self.module, "conf", {"flairs": {"3+": {"rid": "1"}}}):
            await self.cog.remove_trades("42")
        member.remove_roles.assert_awaited_once_with(trade)

    async def test_trade_assignment_resolves_string_role_ids_as_integers(self):
        role = SimpleNamespace(id=1)
        member = SimpleNamespace(name="Test", discriminator="0", add_roles=AsyncMock())
        guild = SimpleNamespace(name="Guild", get_role=Mock(side_effect=lambda role_id: role if role_id == 1 else None), get_member=Mock(return_value=member))
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=guild))
        with patch.object(self.module, "conf", {"flairs": {"3+": {"rid": "1"}}}):
            self.assertTrue(await self.cog.set_trade_role({"discord": {"id": "42"}}, "3+"))
        member.add_roles.assert_awaited_once_with(role)

    async def test_trade_lookup_for_departed_member_returns_no_role(self):
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=SimpleNamespace(get_member=Mock(return_value=None))))
        self.assertIsNone(await self.cog.get_trades("42"))

    async def test_trade_lookup_returns_highest_role_without_modifying_membership(self):
        low = SimpleNamespace(id=1, name="3+")
        high = SimpleNamespace(id=2, name="5+")
        roles = [low, high]
        member = SimpleNamespace(roles=roles, remove_roles=AsyncMock())
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=SimpleNamespace(get_member=Mock(return_value=member))))
        with patch.object(self.module, "conf", {"flairs": {"3+": {"rid": "1"}, "5+": {"rid": "2"}}}):
            self.assertEqual(await self.cog.get_trades("42"), "5+")
        self.assertEqual(roles, [low, high])
        member.remove_roles.assert_not_called()

    async def test_existing_verification_role_is_idempotent(self):
        role = SimpleNamespace(id=101)
        member = SimpleNamespace(roles=[role], add_roles=AsyncMock(), send=AsyncMock())
        guild = SimpleNamespace(get_role=Mock(return_value=role), get_member=Mock(return_value=member))
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=guild))
        self.assertTrue(await self.cog.set_verified("42"))
        member.add_roles.assert_not_called()
        member.send.assert_not_called()

    async def test_forbidden_role_update_does_not_send_success_dm(self):
        error = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "role hierarchy")
        member = SimpleNamespace(roles=[], add_roles=AsyncMock(side_effect=error), send=AsyncMock())
        guild = SimpleNamespace(get_role=Mock(return_value=SimpleNamespace(id=101)), get_member=Mock(return_value=member))
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=guild))
        with self.assertLogs(level="ERROR"):
            self.assertFalse(await self.cog.set_verified("42"))
        member.send.assert_not_called()

    async def test_uncached_member_is_fetched_before_verification(self):
        role = SimpleNamespace(id=101)
        member = SimpleNamespace(roles=[], add_roles=AsyncMock(), send=AsyncMock())
        guild = SimpleNamespace(get_role=Mock(return_value=role), get_member=Mock(return_value=None), fetch_member=AsyncMock(return_value=member))
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=guild))
        self.assertTrue(await self.cog.set_verified("42"))
        guild.fetch_member.assert_awaited_once_with(42)
        member.add_roles.assert_awaited_once_with(role)

    async def test_missing_role_retains_verification_retry(self):
        member = SimpleNamespace(add_roles=AsyncMock())
        guild = SimpleNamespace(get_role=Mock(return_value=None), get_member=Mock(return_value=member))
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=guild))
        self.assertFalse(await self.cog.set_verified("42"))
        member.add_roles.assert_not_called()

    async def test_missing_guild_retains_verification_retry(self):
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=None))
        self.assertFalse(await self.cog.set_verified("42"))

    async def test_role_assignment_reports_success_even_when_the_dm_is_closed(self):
        role = SimpleNamespace(id=101)
        member = SimpleNamespace(id=42, name="Tester", discriminator="0", roles=[],
                                 add_roles=AsyncMock(), send=AsyncMock(side_effect=discord.Forbidden(
                                     SimpleNamespace(status=403, reason="Forbidden"), "DMs closed")))
        guild = SimpleNamespace(name="Test", get_role=Mock(return_value=role), get_member=Mock(return_value=member))
        self.cog.client = SimpleNamespace(get_guild=Mock(return_value=guild))

        self.assertTrue(await self.cog.set_verified("42"))
        member.add_roles.assert_awaited_once_with(role)

    async def test_database_failure_is_logged_without_acknowledging_work(self):
        self.queue.count_documents.side_effect = RuntimeError("database unavailable")
        with self.assertLogs(level="ERROR"):
            await self.cog.monitor_db()
        self.queue.find_one_and_delete.assert_not_called()

    async def test_ready_uses_the_same_retry_safe_queue_processor(self):
        with patch.object(self.cog, "monitor_db", new_callable=AsyncMock) as monitor:
            await self.cog.on_ready()
            monitor.assert_awaited_once_with()

    async def test_missing_queue_user_does_not_block_later_valid_work(self):
        self.queue.find.return_value = AsyncCursor([{"_id": "bad", "ref": "missing"}, {"_id": "good", "ref": "user"}])
        self.users.find_one.side_effect = [None, {"discord": {"id": "42"}}]
        self.cog.set_verified = AsyncMock(return_value=True)
        await self.cog.monitor_db()
        self.cog.set_verified.assert_awaited_once_with("42")
        self.queue.find_one_and_delete.assert_awaited_once_with({"_id": "good"})

    async def test_successful_verification_is_acknowledged(self):
        self.cog.set_verified = AsyncMock(return_value=True)
        await self.cog.monitor_db()
        self.queue.find_one_and_delete.assert_awaited_once_with({"_id": "queued"})

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.module, self.cog = await self.load_cog("verify", "Verify")
        self.queue = SimpleNamespace(
            count_documents=AsyncMock(return_value=1),
            find=Mock(return_value=AsyncCursor([{"_id": "queued", "ref": "user"}])),
            find_one_and_delete=AsyncMock(),
        )
        self.users = SimpleNamespace(find_one=AsyncMock(return_value={"discord": {"id": "42"}}))
        self.users.delete_one = AsyncMock()
        self.confirmation = SimpleNamespace(id=123, add_reaction=AsyncMock(), clear_reactions=AsyncMock())
        self.ctx = SimpleNamespace(author=SimpleNamespace(id=42, roles=[]), send=AsyncMock(return_value=self.confirmation),
                                   guild=SimpleNamespace(me=SimpleNamespace(colour=discord.Colour.blue())))
        self.user_data = {"discord": {"id": "123456789123456789", "username": "tester"},
                          "reddit": {"name": "redditor"}, "verified": True, "verified_at": 1700000000}
        self.enterContext(patch.object(self.module, "db", SimpleNamespace(queue=self.queue, users=self.users)))

    async def test_unsuccessful_verification_remains_queued_for_retry(self):
        self.cog.set_verified = AsyncMock(return_value=False)

        await self.cog.monitor_db()

        self.cog.set_verified.assert_awaited_once_with("42")
        self.queue.find_one_and_delete.assert_not_called()
