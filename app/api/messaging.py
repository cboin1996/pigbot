from models import talk, art
from discord.ext import commands
from discord import Embed
from random import choice

from discord import slash_command


class Common(commands.Cog):
    def __init__(self, bot: commands.bot) -> None:
        self.bot = bot

    @slash_command(description="Generates a random response.")
    async def ree(self, ctx):
        embed = Embed(description=talk.random_response())
        await ctx.respond(embed=embed)

    @slash_command(description="Shows pig art")
    async def art(self, ctx):
        for art_piece in art.PigArt.get_pig_art():
            await ctx.respond(art_piece)

    @slash_command(description="Get a random pig art piece to brighten your day")
    async def random_pig(self, ctx):
        await ctx.respond(choice(art.PigArt.get_pig_art()))
