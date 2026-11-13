from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
import httpx

from tests.support import BotTestCase


HttpClient = httpx.AsyncClient
TEST = {"testResult": "PASSED", "completedDate": "2024.02.03 12:30:00", "expiryDate": "2025.02.03",
        "odometerValue": "10000", "odometerUnit": "mi", "rfrAndComments": [{"text":"Advisory", "type":"ADVISORY"}], "motTestNumber": "123"}
VEHICLE = {"registration": "TEST123", "manufactureYear": "2020", "make": "FORD", "model": "FOCUS",
           "fuelType": "Petrol", "primaryColour": "Blue", "motTests": [TEST]}


class MotTests(BotTestCase):
    async def test_http_not_found_is_reported_as_no_vehicle(self):
        self.http_response(httpx.Response(404))
        await self.invoke(self.cog, "_mot", self.ctx, "UNKNOWN")
        self.assertIn("No vehicle", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_first_used_date_is_used_when_manufacture_year_is_missing(self):
        data = deepcopy(VEHICLE)
        del data["manufactureYear"]
        data["firstUsedDate"] = "2021.02.03"
        self.assertIn("2021 Ford", self.module.Vehicle(data).embeds[0].title)

    async def test_multiple_tests_for_a_year_are_paginated(self):
        data = deepcopy(VEHICLE)
        data["motTests"].append(deepcopy(TEST))
        with patch.object(self.module, "get_vehicle", AsyncMock(return_value=self.module.Vehicle(data))):
            await self.invoke(self.cog, "_mot", self.ctx, "TEST123", year=2024)
        view = self.ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)
        self.assertEqual(len(view.pages), 2)

    async def test_multiple_tests_are_paginated(self):
        data = deepcopy(VEHICLE)
        data["motTests"].append(deepcopy(TEST))
        with patch.object(self.module, "get_vehicle", AsyncMock(return_value=self.module.Vehicle(data))):
            await self.invoke(self.cog, "_mot", self.ctx, "TEST123")
        view = self.ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)
        self.assertEqual(len(view.pages), 2)

    async def test_http_service_failure_is_unavailable_rather_than_vehicle_not_found(self):
        self.http_response(httpx.Response(503, json={"httpStatus":503}))
        await self.invoke(self.cog, "_mot", self.ctx, "TEST123")
        self.assertIn("unavailable", self.ctx.send.call_args.kwargs["embed"].description.lower())

    async def test_unknown_paint_colour_does_not_break_vehicle_results(self):
        vehicle = self.module.Vehicle({**deepcopy(VEHICLE), "primaryColour":"Multi-coloured"})
        self.assertEqual(vehicle.embeds[0].colour, discord.Colour.default())

    async def test_api_timeout_is_reported_as_unavailable(self):
        with patch.object(self.module, "get_vehicle", AsyncMock(side_effect=httpx.ReadTimeout("slow"))):
            await self.invoke(self.cog, "_mot", self.ctx, "TEST123")
        self.assertIn("unavailable", self.ctx.send.call_args.kwargs["embed"].description.lower())

    async def test_missing_year_sends_no_tests_found(self):
        with patch.object(self.module, "get_vehicle", AsyncMock(return_value=self.module.Vehicle(deepcopy(VEHICLE)))):
            await self.invoke(self.cog, "_mot", self.ctx, "TEST123", year=1990)
        self.assertIn("No MOT tests", self.ctx.send.call_args.kwargs["embed"].description)

    async def test_command_selects_only_requested_year(self):
        data = deepcopy(VEHICLE)
        data["motTests"].append({**deepcopy(TEST), "completedDate":"2023.02.03 12:30:00"})
        with patch.object(self.module, "get_vehicle", AsyncMock(return_value=self.module.Vehicle(data))):
            await self.invoke(self.cog, "_mot", self.ctx, "TEST123", year=2023)
        self.assertEqual(self.ctx.send.call_args.kwargs["embed"].fields[1].value, "03/02/2023")

    async def test_vehicle_without_tests_shows_basic_expiry(self):
        data = deepcopy(VEHICLE)
        del data["motTests"]
        data["motTestExpiryDate"] = "2025-02-03"
        vehicle = self.module.Vehicle(data)
        self.assertEqual(vehicle.embeds[0].fields[0].value, "03/02/2025")

    async def test_failed_test_does_not_require_an_expiry_date(self):
        data = deepcopy(TEST)
        data["testResult"] = "FAILED"
        del data["expiryDate"]
        vehicle = self.module.Vehicle({**deepcopy(VEHICLE), "motTests":[data]})
        self.assertEqual({f.name:f.value for f in vehicle.embeds[0].fields}["MOT Expiry"], "N/A")

    async def test_no_vehicle_response_is_not_a_parser_crash(self):
        self.http_response(httpx.Response(200, json=[]))
        self.assertIsNone(await self.module.get_vehicle("UNKNOWN"))

    async def test_single_vehicle_result_is_returned_through_real_httpx(self):
        self.http_response(httpx.Response(200, json=[VEHICLE]))
        vehicle = await self.module.get_vehicle("TEST123")
        self.assertEqual(vehicle.registration, "TEST123")

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.module, self.cog = await self.load_cog("mot", "MOT")
        self.ctx = SimpleNamespace(send=AsyncMock(), author=SimpleNamespace(id=42),
                                   guild=SimpleNamespace(me=SimpleNamespace(colour=discord.Colour.blue())))

    def http_response(self, response):
        transport = httpx.MockTransport(lambda request: response)
        self.enterContext(patch.object(self.module.httpx, "AsyncClient", side_effect=lambda: HttpClient(transport=transport)))

    async def test_vehicle_and_test_fixture_render_expected_fields(self):
        vehicle = self.module.Vehicle(deepcopy(VEHICLE))
        self.assertEqual(vehicle.embeds[0].title, "2020 Ford Focus")
        fields = {field.name: field.value for field in vehicle.embeds[0].fields}
        self.assertEqual(fields["MOT Mileage"], "10,000mi")
        self.assertEqual(fields["MOT Result"], "PASSED")
        self.assertEqual(fields["MOT Expiry"], "03/02/2025")
