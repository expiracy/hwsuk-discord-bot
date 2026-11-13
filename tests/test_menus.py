import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from unity_util.menus import menu


class MenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_page_sends_the_embed_without_controls(self):
        embed = discord.Embed(title="Result")
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock())

        message = await menu(ctx, [embed])

        ctx.send.assert_awaited_once_with(embed=embed)
        self.assertIs(message, ctx.send.return_value)

    async def test_next_button_wraps_to_first_page(self):
        pages = [discord.Embed(title="First"), discord.Embed(title="Second")]
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock())
        await menu(ctx, pages, page=1)
        view = ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)
        interaction = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()))

        await view.children[1].callback(interaction)

        interaction.response.edit_message.assert_awaited_once_with(embed=pages[0], view=view)

    async def test_previous_button_wraps_to_last_page(self):
        pages = [discord.Embed(title="First"), discord.Embed(title="Second")]
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock())
        await menu(ctx, pages)
        view = ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)
        interaction = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()))

        await view.children[0].callback(interaction)

        interaction.response.edit_message.assert_awaited_once_with(embed=pages[1], view=view)

    async def test_other_users_cannot_change_pages(self):
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock())
        await menu(ctx, [discord.Embed(title="First"), discord.Embed(title="Second")])
        view = ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)
        interaction = SimpleNamespace(user=SimpleNamespace(id=2), response=SimpleNamespace(send_message=AsyncMock()))

        allowed = await view.interaction_check(interaction)

        self.assertFalse(allowed)
        self.assertEqual(view.page, 0)
        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(interaction.response.send_message.call_args.kwargs["ephemeral"])

    async def test_requester_can_change_pages(self):
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock())
        await menu(ctx, [discord.Embed(title="First"), discord.Embed(title="Second")])
        view = ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)
        interaction = SimpleNamespace(user=SimpleNamespace(id=1), response=SimpleNamespace(send_message=AsyncMock()))

        self.assertTrue(await view.interaction_check(interaction))
        interaction.response.send_message.assert_not_called()

    async def test_timeout_disables_buttons_on_the_message(self):
        message = SimpleNamespace(edit=AsyncMock())
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock(return_value=message))
        await menu(ctx, [discord.Embed(title="First"), discord.Embed(title="Second")])
        view = ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)

        await view.on_timeout()

        self.assertTrue(all(button.disabled for button in view.children))
        message.edit.assert_awaited_once_with(view=view)

    async def test_empty_results_are_rejected_without_sending_a_message(self):
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock())

        with self.assertRaisesRegex(ValueError, "at least one page"):
            await menu(ctx, [])

        ctx.send.assert_not_called()

    async def test_invalid_page_is_rejected_without_sending_a_message(self):
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock())

        with self.assertRaisesRegex(ValueError, "out of range"):
            await menu(ctx, [discord.Embed(title="First")], page=-1)

        ctx.send.assert_not_called()

    async def test_multiple_pages_show_requested_page_with_arrow_buttons(self):
        pages = [discord.Embed(title="First"), discord.Embed(title="Second")]
        ctx = SimpleNamespace(author=SimpleNamespace(id=1), send=AsyncMock())

        message = await menu(ctx, pages, page=1, timeout=120)

        self.assertIs(ctx.send.call_args.kwargs["embed"], pages[1])
        self.assertIn("view", ctx.send.call_args.kwargs)
        view = ctx.send.call_args.kwargs["view"]
        self.addCleanup(view.stop)
        self.assertEqual([str(button.emoji) for button in view.children], ["⬅️", "➡️"])
        self.assertEqual(view.timeout, 120)
        self.assertIs(message, ctx.send.return_value)
