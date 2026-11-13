from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.support import BotTestCase


class UslTests(BotTestCase):
    async def test_non_banned_result_has_no_warning_footer(self):
        embed = self.cog.make_embed({"person":"tester", "banned":False})
        self.assertEqual(embed.fields[1].value, "No")

    async def test_upstream_error_is_reported(self):
        with patch.object(self.module.usl, "fetch_usl_user_data", AsyncMock(side_effect=RuntimeError("down"))):
            await self.invoke(self.cog, "query_universal_scammer_list", self.ctx, username="tester")
        self.assertIn("Something went wrong", self.ctx.send.call_args.args[0])

    async def test_reddit_prefix_is_removed_before_lookup(self):
        with patch.object(self.module.usl, "fetch_usl_user_data", AsyncMock(return_value={"person":"tester", "banned":True})) as fetch:
            await self.invoke(self.cog, "query_universal_scammer_list", self.ctx, username="/u/tester")
            fetch.assert_awaited_once_with("tester")
        self.assertIn("DO NOT trade", self.ctx.send.call_args.kwargs["embed"].footer.text)

    async def test_invalid_username_does_not_call_service(self):
        with patch.object(self.module.usl, "fetch_usl_user_data", new_callable=AsyncMock) as fetch:
            await self.invoke(self.cog, "query_universal_scammer_list", self.ctx, username="invalid name")
            fetch.assert_not_called()
        self.assertIn("Invalid username", self.ctx.send.call_args.args[0])

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.module, self.cog = await self.load_cog("usl", "UniversalScammerList")
        self.ctx = SimpleNamespace(send=AsyncMock())

    async def test_disabled_service_returns_unknown_without_crashing_or_marking_safe(self):
        await self.invoke(self.cog, "query_universal_scammer_list", self.ctx, username="tester")
        response = str(self.ctx.send.call_args).lower()
        self.assertTrue("unavailable" in response or "unknown" in response)
