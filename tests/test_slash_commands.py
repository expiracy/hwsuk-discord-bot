import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from tests.slash_support import SlashBotTestCase


class SlashCommandTests(SlashBotTestCase):
    async def test_verify_is_a_slash_command_and_replies_with_the_verification_link(self):
        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.load_extension("unity_cogs.verify")
        command = self.client.tree.get_command("verify")
        self.assertIsNotNone(command)
        interaction = self.interaction(command)

        await command.callback(command.binding, interaction)

        interaction.response.defer.assert_awaited_once()
        self.assertEqual(
            interaction.followup.send.call_args.kwargs["embed"].url,
            "https://verify.hardwareswap.uk",
        )
        self.assertIsNone(self.client.get_command("verify"))

    async def test_cex_slash_search_acknowledges_before_fetching_results(self):
        await self.client.load_extension("unity_cogs.cex")
        command = self.client.tree.get_command("search")
        self.assertIsNotNone(command)
        interaction = self.interaction(command)

        async def search(term):
            self.assertTrue(interaction.response.is_done())
            self.assertEqual(term, "rtx 3060")
            return ()

        command.binding.cex_search = AsyncMock(side_effect=search)
        await command.callback(command.binding, interaction, search_term="rtx 3060")

        self.assertIn("No products found", interaction.followup.send.call_args.kwargs["embed"].description)

    async def test_verification_alias_is_a_slash_command_and_unloads_with_its_cog(self):
        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.load_extension("unity_cogs.verify")
        alias = self.client.tree.get_command("verification")
        self.assertIsNotNone(alias)
        interaction = self.interaction(alias)

        await alias.callback(alias.binding, interaction)

        self.assertEqual(interaction.followup.send.call_args.kwargs["embed"].title, "Verify here!")
        await self.client.unload_extension("unity_cogs.verify")
        self.assertIsNone(self.client.tree.get_command("verification"))

    async def test_verification_commands_expose_typed_slash_options(self):
        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.load_extension("unity_cogs.verify")
        cog = self.client.get_cog("Verify")

        self.assertEqual({command.name for command in cog.get_app_commands() if "alias_for" not in command.extras}, {
            "verify", "whois", "editflair", "status", "removeuser",
        })
        self.assertEqual(cog.get_commands(), [])
        options = self.client.tree.get_command("editflair").to_dict(self.client.tree)["options"]
        self.assertEqual([(option["name"], option["type"], option["required"]) for option in options], [
            ("user", 3, True), ("flair", 3, True),
        ])

    async def test_whois_defers_before_looking_up_a_mention_from_a_slash_option(self):
        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.load_extension("unity_cogs.verify")
        command = self.client.tree.get_command("whois")
        interaction = self.interaction(command)
        user = {"discord": {"id": "123456789123456789"}}

        async def lookup(query):
            self.assertTrue(interaction.response.is_done())
            if query.get("discord.id", {}).get("$regex") == "^123456789123456789$":
                return user
            return None

        module = importlib.import_module(command.module)
        db = SimpleNamespace(users=SimpleNamespace(find_one=AsyncMock(side_effect=lookup)))
        command.binding.make_whois_embed = AsyncMock(return_value=discord.Embed(title="Whois"))
        with patch.object(module, "db", db):
            await command.callback(command.binding, interaction, "<@123456789123456789>")

        command.binding.make_whois_embed.assert_awaited_once_with(user)
        self.assertEqual(interaction.followup.send.call_args.kwargs["embed"].title, "Whois")

    async def test_limiter_whitelist_is_a_member_subcommand_restricted_to_moderators(self):
        await self.client.load_extension("unity_cogs.limiter")
        group = self.client.tree.get_command("limiter")
        self.assertIsNotNone(group)
        command = group.get_command("whitelist")
        options = command.to_dict(self.client.tree)["options"]
        self.assertEqual([(option["name"], option["type"]) for option in options], [("member", 6), ("seconds", 4)])
        interaction = self.interaction(command)

        with self.assertRaises(discord.app_commands.MissingPermissions):
            await command._check_can_run(interaction)

        interaction.permissions = discord.Permissions(manage_roles=True)
        self.assertTrue(await command._check_can_run(interaction))

    async def test_notes_are_slash_subcommands_restricted_to_moderators(self):
        with patch("motor.motor_asyncio.AsyncIOMotorClient"):
            await self.client.load_extension("unity_cogs.notes")
        group = self.client.tree.get_command("notes")
        self.assertIsNotNone(group)
        self.assertEqual({command.name for command in group.commands}, {
            "view", "find", "delete", "remove", "create", "add", "new",
        })
        for command in group.commands:
            interaction = self.interaction(command)
            with self.assertRaises(discord.app_commands.MissingPermissions):
                await command._check_can_run(interaction)
            interaction.permissions = discord.Permissions(manage_roles=True)
            self.assertTrue(await command._check_can_run(interaction))
        self.assertEqual(self.client.get_cog("Notes").get_commands(), [])

    async def test_notes_create_takes_required_content_from_the_slash_option(self):
        with patch("motor.motor_asyncio.AsyncIOMotorClient"):
            await self.client.load_extension("unity_cogs.notes")
        command = self.client.tree.get_command("notes").get_command("create")
        option = next(option for option in command.to_dict(self.client.tree)["options"] if option["name"] == "note_content")
        self.assertTrue(option["required"])
        interaction = self.interaction(command)
        command.binding.gen_hash = AsyncMock(return_value="abc1234")
        notes = SimpleNamespace(insert_one=AsyncMock())
        module = importlib.import_module(command.module)

        with patch.object(module, "db", SimpleNamespace(notes=notes)):
            await command.callback(command.binding, interaction, SimpleNamespace(id=17), "Trade resolved")

        note = notes.insert_one.call_args.args[0]
        self.assertEqual((note["user"], note["content"], note["added_by"]), ("17", "Trade resolved", "42"))
        interaction.response.defer.assert_awaited_once()

    async def test_ebay_price_check_and_its_aliases_are_slash_commands(self):
        await self.client.load_extension("unity_cogs.ebay")
        command = self.client.tree.get_command("check")
        self.assertIsNotNone(command)
        self.assertTrue({"check", "pc", "chk", "price", "pricecheck"}.issubset(
            {command.name for command in self.client.tree.get_commands()}
        ))
        interaction = self.interaction(command)

        async def fetch(term):
            self.assertTrue(interaction.response.is_done())
            return None

        command.binding.make_soup = AsyncMock(side_effect=fetch)
        await command.callback(command.binding, interaction, search_term="rtx 3060")

        self.assertEqual(interaction.followup.send.call_args.kwargs["embed"].title, "Error")

    async def test_usl_slash_command_defers_before_querying_the_service(self):
        await self.client.load_extension("unity_cogs.usl")
        command = self.client.tree.get_command("usl")
        self.assertIsNotNone(command)
        interaction = self.interaction(command)

        async def query(username):
            self.assertTrue(interaction.response.is_done())
            self.assertEqual(username, "example")
            return {"banned": False, "person": username}

        module = importlib.import_module(command.module)
        with patch.object(module.usl, "fetch_usl_user_data", new=AsyncMock(side_effect=query)):
            await command.callback(command.binding, interaction, username="u/example")

        self.assertEqual(interaction.followup.send.call_args.kwargs["embed"].title, "USL Search Results")

    async def test_mot_slash_command_has_registration_and_optional_year_options(self):
        await self.client.load_extension("unity_cogs.mot")
        command = self.client.tree.get_command("mot")
        self.assertIsNotNone(command)
        options = command.to_dict(self.client.tree)["options"]
        self.assertEqual([(option["name"], option["type"], option["required"]) for option in options], [
            ("registration", 3, True), ("year", 4, False),
        ])
        interaction = self.interaction(command)

        async def get_vehicle(registration):
            self.assertTrue(interaction.response.is_done())
            return None

        module = importlib.import_module(command.module)
        with patch.object(module, "get_vehicle", new=AsyncMock(side_effect=get_vehicle)):
            await command.callback(command.binding, interaction, "AB12CDE")

        self.assertEqual(interaction.followup.send.call_args.kwargs["embed"].description, "No vehicle found matching that registration")

    async def test_help_lists_slash_commands_instead_of_registering_prefix_help(self):
        application = await self.use_application()
        application.conf["preloaded"] = ["verify"]
        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.setup_hook()
        command = self.client.tree.get_command("help")
        self.assertIsNotNone(command)
        interaction = self.interaction(command)

        await command.callback(interaction)

        self.assertIn("/verify", interaction.followup.send.call_args.kwargs["embed"].description)
        self.assertIsNone(self.client.get_command("help"))

    async def test_startup_syncs_commands_to_the_configured_server_after_loading_extensions(self):
        application = await self.use_application()
        application.conf["preloaded"] = ["cex"]

        async def sync(*, guild):
            self.assertEqual(guild.id, 1)
            commands = self.client.tree.get_commands(guild=guild)
            self.assertIn("search", {command.name for command in commands})
            return []

        self.client.tree.sync.side_effect = sync
        await self.client.setup_hook()

        self.client.tree.sync.assert_awaited_once()

    async def test_owner_slash_commands_reject_other_users_without_changing_extensions(self):
        await self.use_application()
        self.client.is_owner = AsyncMock(return_value=False)

        for name in ("load", "unload", "reload"):
            command = self.client.tree.get_command(name)
            interaction = self.interaction(command)
            with self.assertRaises(discord.app_commands.CheckFailure) as denied:
                await command._check_can_run(interaction)
            await self.client.tree.on_error(interaction, denied.exception)
            interaction.response.send_message.assert_awaited_once()
            self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])
        self.assertFalse(self.client.extensions)
        self.client.tree.sync.assert_not_called()

        self.client.is_owner.return_value = True
        self.assertTrue(await self.client.tree.get_command("load")._check_can_run(interaction))

    async def test_extension_management_responses_are_deferred_privately(self):
        await self.use_application()
        command = self.client.tree.get_command("load")
        interaction = self.interaction(command)

        await command.callback(interaction, "feedback")

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    async def test_failed_startup_sync_logs_the_server_and_stops_startup(self):
        await self.use_application()
        failure = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Missing Access")
        self.client.tree.sync.side_effect = failure

        with self.assertLogs(level="ERROR") as logs:
            with self.assertRaises(discord.Forbidden):
                await self.client.setup_hook()

        self.assertIn("slash", "\n".join(logs.output))
        self.assertIn("guild 1", "\n".join(logs.output))

    async def test_all_configured_commands_serialize_as_slash_commands_without_prefix_commands(self):
        application = await self.use_application()
        application.conf = json.loads(Path("config.json").read_text())
        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.setup_hook()

        self.assertEqual(set(self.client.all_commands), set())
        expected = {
            "help", "load", "unload", "reload", "verify", "verification", "whois", "editflair",
            "status", "removeuser", "remove_user", "search", "limiter", "check", "pc", "chk",
            "price", "pricecheck", "notes", "mot", "usl",
        }
        self.assertEqual({command.name for command in self.client.tree.get_commands()}, expected)
        guild = discord.Object(id=1)
        payload = [command.to_dict(self.client.tree) for command in self.client.tree.get_commands(guild=guild)]
        self.assertEqual({command["name"] for command in json.loads(json.dumps(payload))}, expected)
        self.assertEqual(self.client.tree.get_command("notes").default_permissions, discord.Permissions(manage_roles=True))

    async def test_trade_update_and_user_removal_keep_the_updater_role_check(self):
        with patch("motor.motor_asyncio.AsyncIOMotorClient"), patch("praw.Reddit"):
            await self.client.load_extension("unity_cogs.verify")
        cog = self.client.get_cog("Verify")
        cog.get_user = AsyncMock(return_value={})

        for name in ("editflair", "removeuser"):
            command = self.client.tree.get_command(name)
            interaction = self.interaction(command)
            options = {"user": "example"}
            if name == "editflair":
                options["flair"] = "3+"
            await command.callback(command.binding, interaction, **options)
            self.assertIn("permission", interaction.followup.send.call_args.kwargs["embed"].description)
        cog.get_user.assert_not_called()

        command = self.client.tree.get_command("editflair")
        interaction = self.interaction(command, user=SimpleNamespace(id=42, roles=[SimpleNamespace(id=100)]))
        await command.callback(command.binding, interaction, user="example", flair="3+")
        cog.get_user.assert_awaited_once_with("example")
