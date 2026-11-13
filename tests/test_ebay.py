from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from bs4 import BeautifulSoup

from tests.support import BotTestCase


class EbayTests(BotTestCase):
    async def test_http_request_preserves_special_characters_in_the_search_query(self):
        real_client = httpx.AsyncClient
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, text='<ul class="srp-results"></ul>')
        transport = httpx.MockTransport(respond)
        with patch.object(self.module.httpx, "AsyncClient", side_effect=lambda: real_client(transport=transport)):
            page = await self.cog.make_soup("dell & lenovo")
        self.assertEqual(requests[0].url.params["_nkw"], "dell & lenovo")
        self.assertIsNotNone(page.find("ul", class_="srp-results"))

    async def test_connection_errors_return_an_error_response(self):
        self.cog.make_soup = AsyncMock(side_effect=httpx.ConnectError("connection failed"))
        await self.invoke(self.cog, "check", self.ctx, search_term="dell laptop")
        self.assertEqual(self.ctx.send.call_args.kwargs["embed"].title, "Error")

    async def test_successful_price_check_excludes_outliers(self):
        self.cog.make_soup = AsyncMock(return_value=BeautifulSoup('<ul class="srp-results">' + ''.join(f'<li class="s-item" data-price="{p}"></li>' for p in [10,20,30,40,1000]) + '</ul>', "html.parser"))
        self.cog.get_product_info = lambda product: {"title": "dell laptop", "price": float(product["data-price"])}
        await self.invoke(self.cog, "check", self.ctx, search_term="dell laptop")
        embed = self.ctx.send.call_args.kwargs["embed"]
        self.assertEqual(embed.fields[2].value, "£30.00")
        self.assertEqual(embed.fields[4].value, "3")

    async def test_invalid_listing_is_skipped(self):
        self.assertEqual(self.cog.get_product_info(BeautifulSoup("<li>ad</li>", "html.parser").li), {})

    async def test_obfuscated_sold_date_ignores_dummy_characters(self):
        tags = BeautifulSoup('<span class="noise">junk</span><span class="real">Sold </span><span class="real"></span><span class="real">12 Jan 2024</span>', "html.parser").contents
        self.assertEqual(self.cog.build_date_string(tags), "12 Jan 2024")

    async def test_completed_listing_price_includes_postage(self):
        product = BeautifulSoup('<li><span class="s-item__price">£1,000.50</span><span class="s-item__logisticsCost">+ £5.00 postage</span></li>', "html.parser").li
        self.assertEqual(self.cog.parse_price(product), 1005.50)

    async def test_timeout_returns_a_response(self):
        self.cog.make_soup = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
        await self.invoke(self.cog, "check", self.ctx, search_term="dell laptop")
        self.assertEqual(self.ctx.send.call_args.kwargs["embed"].title, "Error")

    async def test_captcha_page_returns_parse_error_without_claiming_no_products(self):
        self.cog.make_soup = AsyncMock(return_value=BeautifulSoup("<html>challenge</html>", "html.parser"))
        await self.invoke(self.cog, "check", self.ctx, search_term="dell laptop")
        self.assertIn("parsing", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_variance_is_range_as_percentage_of_mean(self):
        self.assertEqual(self.cog.determine_variance([10, 30, 20]), 100)

    async def test_quartiles_sort_and_interpolate_prices(self):
        self.assertEqual(self.cog.find_quartiles([40, 10, 30, 20]), [15, 25, 35])

    async def test_quartiles_for_two_items(self):
        self.assertEqual(self.cog.find_quartiles([30, 10]), [10, 20, 30])

    async def test_quartiles_for_single_item(self):
        self.assertEqual(self.cog.find_quartiles([25]), [25, 25, 25])

    async def test_quartiles_handle_empty_results(self):
        self.assertEqual(self.cog.find_quartiles([]), [0, 0, 0])

    async def test_explicit_exclusions_are_applied_case_insensitively(self):
        term, excluded = self.cog.get_filter("dell laptop -broken")
        self.assertEqual(term, "dell laptop")
        self.assertTrue(self.cog.filtered_out("Dell Laptop BROKEN", excluded))
        self.assertFalse(self.cog.filtered_out("Dell Laptop", excluded))

    async def test_short_search_is_rejected_before_http(self):
        self.cog.make_soup = AsyncMock()
        await self.invoke(self.cog, "check", self.ctx, search_term="gpu")
        self.cog.make_soup.assert_not_called()
        self.assertEqual(self.ctx.send.call_args.kwargs["embed"].title, "Error")

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.module, self.cog = await self.load_cog("ebay", "Ebay")
        self.ctx = SimpleNamespace(send=AsyncMock())

    async def test_search_words_are_not_accidentally_left_in_the_exclusion_filter(self):
        term, excluded = self.cog.get_filter("iphone pro plus")
        self.assertEqual(term, "iphone pro plus")
        self.assertFalse(self.cog.filtered_out("iPhone Pro Plus", excluded))
