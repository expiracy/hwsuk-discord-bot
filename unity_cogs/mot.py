import discord
from discord import app_commands
from discord.ext import commands
import httpx
import logging
import sys
from unity_util import bot_config
from datetime import datetime as dt
from colour import Color as Colour
from unity_util.menus import menu
from unity_util.slash_commands import command_context



class OdometerReading:
    def __init__(self, value: str, unit: str):
        self.value: int = int(value)
        self.unit: str = unit

class Comment:
    def __init__(self, data: dict):
        self.text: str = data['text']
        self.type: str = data['type']

class MotTest:
    def __init__(self, test):
        self.result: str = test['testResult']
        self.completed_date = dt.strptime(test['completedDate'], '%Y.%m.%d %H:%M:%S')
        if self.result != 'FAILED':
            self.expiry_date = dt.strptime(test['expiryDate'], '%Y.%m.%d')
        self.odometer_reading: OdometerReading = OdometerReading(test['odometerValue'], test['odometerUnit'])
        self.comments: tuple[Comment] = tuple([Comment(i) for i in test['rfrAndComments']])
        self.id = int(test['motTestNumber'])

class Vehicle:
    def __init__(self, data:dict):
        self.registration = data['registration']
        if 'manufactureYear' in data:
            self.registration_date = dt.strptime(data['manufactureYear'], '%Y')
        else:
            self.registration_date = dt.strptime(data['firstUsedDate'], '%Y.%m.%d')
        self.make = data['make'].capitalize()
        self.model = data['model'].capitalize()
        self.fuel_type = data['fuelType']
        self.colour = data['primaryColour']
        try:
            rgb = Colour(self.colour).rgb
            self.embed_colour = discord.Colour.from_rgb(*(int(component * 255) for component in rgb))
        except ValueError:
            self.embed_colour = discord.Colour.default()
        self.tests = tuple([MotTest(i) for i in data['motTests']]) if 'motTests' in data else tuple([])
        if self.tests:
            self.embeds = tuple([self.make_embed(i) for i in range(len(self.tests))])
        else:
            self.mot_expiry_date = dt.strptime(data['motTestExpiryDate'], '%Y-%m-%d')
            self.embeds = tuple([self.make_basic_embed()])

    def make_basic_embed(self):
        embed = discord.Embed(title=f'{self.registration_date.year} {self.make} {self.model}', colour=self.embed_colour)
        embed.add_field(name='MOT Expiry', value=self.mot_expiry_date.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name='Colour', value=self.colour, inline=True)
        return embed

    def make_embed(self, test_index) -> discord.Embed:
        test = self.tests[test_index]
        embed = discord.Embed(title=f'{self.registration_date.year} {self.make} {self.model}', colour=self.embed_colour)
        embed.add_field(name='MOT Result', value=test.result, inline=True)
        embed.add_field(name='MOT Date', value=test.completed_date.strftime("%d/%m/%Y"), inline=True)
        if test.result != 'FAILED':
            embed.add_field(name='MOT Expiry', value=test.expiry_date.strftime("%d/%m/%Y"), inline=True)
        else:
            embed.add_field(name='MOT Expiry', value='N/A', inline=True)
        embed.add_field(name='MOT Mileage', value=f'{"{:,}".format(test.odometer_reading.value)}{test.odometer_reading.unit}', inline=True)
        embed.add_field(name='MOT Number', value=test.id, inline=True)
        embed.add_field(name='Car Colour', value=self.colour, inline=True)
        return embed

async def get_vehicle(registration: str) -> Vehicle:
    headers = {'x-api-key': bot_config.DVLA_API_KEY}
    url = f'https://beta.check-mot.service.gov.uk/trade/vehicles/mot-tests/?registration={registration}'
    async with httpx.AsyncClient() as client:
        data = await client.get(url, headers=headers)
        if data.status_code == 404:
            return None
        data.raise_for_status()
        json = data.json()

    if not json or 'httpStatus' in json: # 404 or no results
        return None

    return Vehicle(json[0])

class MOT(commands.Cog):

    def __init__(self, client):
        self.client = client

# Events

    @commands.Cog.listener()
    async def on_ready(self):
        print('MOT search cog online')

# Commands

    @app_commands.command(name='mot', description="Look up a vehicle's MOT history")
    @app_commands.describe(registration="Vehicle registration number", year="Only show MOT tests from this year")
    async def _mot(self, interaction: discord.Interaction, registration: str, year: int = 0):
        ctx = await command_context(interaction)
        try:
            vehicle = await get_vehicle(registration)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            logging.warning('MOT service returned an unavailable or invalid response')
            await ctx.send(embed=self.make_error_embed(ctx, 'serviceUnavailable'))
            return

        if not vehicle:
            error_embed = self.make_error_embed(ctx, 'noVehicleFound')
            await ctx.send(embed=error_embed)
            return

        if year:
            mot_tests = [vehicle.tests.index(i) for i in vehicle.tests if i.completed_date.year == year]

            if not mot_tests:
                error_embed = self.make_error_embed(ctx, 'noTestsFound')
                await ctx.send(embed=error_embed)
                return

            mot_embeds = [vehicle.make_embed(i) for i in mot_tests]

            if len(mot_embeds) == 1:
                await ctx.send(embed=mot_embeds[0])
                return

            await menu(ctx, pages=mot_embeds, page=0, timeout=180)

        else:

            if len(vehicle.embeds) == 1:
                await ctx.send(embed=vehicle.embeds[0])
                return

            await menu(ctx, pages=vehicle.embeds, page=0, timeout=120)

    def make_error_embed(self, ctx, error_type: str) -> discord.Embed:
        error_codes = {
            'serviceUnavailable': 'The MOT service is currently unavailable. Please try again later.',
            'noVehicleFound': 'No vehicle found matching that registration',
            'noTestsFound': 'No MOT tests exist for that year'
        }
        return discord.Embed(description=error_codes[error_type], colour=ctx.guild.me.colour if ctx.guild else None)

async def setup(client):
    await client.add_cog(MOT(client))
