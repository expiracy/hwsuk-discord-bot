import discord


async def clear_reactions(message):
    try:
        await message.clear_reactions()
    except discord.HTTPException:
        pass


class PaginationView(discord.ui.View):
    def __init__(self, author_id, pages, page, timeout):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.pages = pages
        self.page = page
        self.message = None

    async def interaction_check(self, interaction):
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Only the person who requested these results can change pages.", ephemeral=True
        )
        return False

    async def on_timeout(self):
        for button in self.children:
            button.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction, button):
        self.page = (self.page - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction, button):
        self.page = (self.page + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)


async def menu(ctx, pages, page=0, timeout=180):
    if not pages:
        raise ValueError('A menu needs at least one page')
    if not 0 <= page < len(pages):
        raise ValueError('Menu page is out of range')
    if len(pages) > 1:
        view = PaginationView(ctx.author.id, pages, page, timeout)
        view.message = await ctx.send(embed=pages[page], view=view)
        return view.message
    return await ctx.send(embed=pages[page])
