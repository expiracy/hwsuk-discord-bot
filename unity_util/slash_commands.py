from copy import copy

from discord import app_commands
from discord.ext import commands


def command_alias(command, name):
    alias = copy(command)
    alias.name = name
    alias.extras = {**command.extras, "alias_for": command.qualified_name}
    if command.parent is not None:
        command.parent.add_command(alias)
    return alias


async def command_context(interaction, *, ephemeral=False):
    ctx = await commands.Context.from_interaction(interaction)
    await ctx.defer(ephemeral=ephemeral)
    return ctx


async def is_owner(interaction):
    if await interaction.client.is_owner(interaction.user):
        return True
    raise app_commands.CheckFailure('Only the bot owner can manage extensions.')
