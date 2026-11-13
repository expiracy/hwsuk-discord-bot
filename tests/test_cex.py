from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import httpx

from tests.support import BotTestCase


HttpClient = httpx.AsyncClient
PRODUCT = {
    "boxId": "GPU42", "boxName": "Graphics card", "sellPrice": 99.99,
    "cashPrice": 50, "exchangePrice": 60, "boxRating": 4.5,
    "imageUrls": {"large": "https://example.com/gpu one.png"},
    "outOfEcomStock": 0, "ecomQuantityOnHand": 2, "categoryFriendlyName": "Graphics Cards",
}


class CexTests(BotTestCase):
    async def test_product_url_preserves_case_in_the_product_id(self):
        self.cog.client = SimpleNamespace(user=SimpleNamespace(id=999))
        self.cog.cex_search = AsyncMock(return_value=(PRODUCT,))
        message = SimpleNamespace(author=SimpleNamespace(id=42, bot=False), content="https://uk.webuy.com/product-detail?id=GPU42", edit=AsyncMock(), channel=SimpleNamespace(send=AsyncMock()))
        await self.cog.on_message(message)
        self.cog.cex_search.assert_awaited_once_with("GPU42")

    async def test_http_timeout_does_not_crash_search(self):
        def fail(request):
            raise httpx.ReadTimeout("upstream timeout")
        transport = httpx.MockTransport(fail)
        with patch.object(self.module.httpx, "AsyncClient", side_effect=lambda: HttpClient(transport=transport)):
            self.assertEqual(await self.cog.cex_search("gpu"), ())

    async def test_malformed_success_response_does_not_crash_the_command(self):
        self.http_response(httpx.Response(200, json={"unexpected": True}))
        self.assertEqual(await self.cog.cex_search("gpu"), ())

    async def test_out_of_range_result_selection_falls_back_to_first_page(self):
        self.cog.cex_search = AsyncMock(return_value=(PRODUCT, PRODUCT))
        await self.invoke(self.cog, "search", self.ctx, search_term="gpu r=99")
        view = self.ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)
        self.assertEqual(self.ctx.send.call_args.kwargs["embed"].footer.text, "1 of 2")

    async def test_non_success_http_response_has_no_results(self):
        self.http_response(httpx.Response(503))
        self.assertEqual(await self.cog.cex_search("gpu"), ())

    async def test_http_response_is_parsed_with_the_real_httpx_client(self):
        self.http_response(httpx.Response(200, json={"response": {"data": {"boxes": [PRODUCT]}}}))
        self.assertEqual(await self.cog.cex_search("gpu & case"), (PRODUCT,))

    async def test_empty_results_produce_a_clear_response(self):
        self.cog.cex_search = AsyncMock(return_value=())
        await self.invoke(self.cog, "search", self.ctx, search_term="missing product")
        self.assertIn("No products", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_single_result_command_sends_prices_and_product_link(self):
        self.cog.cex_search = AsyncMock(return_value=(PRODUCT,))
        await self.invoke(self.cog, "search", self.ctx, search_term="graphics card")
        embed = self.ctx.send.call_args.kwargs["embed"]
        self.assertEqual(embed.author.name, "Graphics card")
        self.assertIn("GPU42", embed.url)
        self.assertEqual(embed.fields[0].value, "£99.99")
        self.assertIn("%20", embed.thumbnail.url)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.module, self.cog = await self.load_cog("cex", "Cex")
        self.ctx = SimpleNamespace(send=AsyncMock(), author=SimpleNamespace(id=42))

    def http_response(self, response):
        transport = httpx.MockTransport(lambda request: response)
        self.enterContext(patch.object(self.module.httpx, "AsyncClient", side_effect=lambda: HttpClient(transport=transport)))

    async def test_homepage_link_is_ignored_without_a_product_id(self):
        self.cog.client = SimpleNamespace(user=SimpleNamespace(id=999))
        self.cog.cex_search = AsyncMock()
        message = SimpleNamespace(author=SimpleNamespace(bot=False, id=42), content="https://uk.webuy.com/")
        await self.cog.on_message(message)
        self.cog.cex_search.assert_not_called()
