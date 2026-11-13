from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from tests.support import BotTestCase


class SlashBotTestCase(BotTestCase):
    async def use_application(self):
        application = await super().use_application()
        self.enterContext(patch.object(self.client.tree, "sync", new_callable=AsyncMock, return_value=[]))
        return application

    def interaction(self, command, *, user=None, permissions=None):
        acknowledged = False

        async def acknowledge(*args, **kwargs):
            nonlocal acknowledged
            acknowledged = True
            return SimpleNamespace(resource=None)

        message = SimpleNamespace(id=123, add_reaction=AsyncMock(), clear_reactions=AsyncMock(), edit=AsyncMock())
        guild = SimpleNamespace(id=1, me=SimpleNamespace(colour=discord.Colour.blue()))
        interaction = Mock(spec=discord.Interaction)
        interaction.client = self.client
        interaction.command = command
        interaction.command_failed = False
        interaction.id = discord.utils.time_snowflake(discord.utils.utcnow())
        interaction.data = {"type": 1}
        interaction._state = self.client._connection
        interaction.message = None
        interaction.namespace = []
        interaction.channel_id = 2
        interaction.channel = SimpleNamespace(id=2, guild=guild)
        interaction.guild = guild
        interaction.guild_id = guild.id
        interaction.user = user or SimpleNamespace(id=42, roles=[], bot=False)
        interaction.permissions = permissions or discord.Permissions.none()
        interaction.is_expired.return_value = False
        interaction.response = SimpleNamespace(
            is_done=lambda: acknowledged,
            defer=AsyncMock(side_effect=acknowledge),
            send_message=AsyncMock(side_effect=acknowledge),
        )
        interaction.followup = SimpleNamespace(send=AsyncMock(return_value=message))
        interaction.original_response = AsyncMock(return_value=message)
        return interaction
