from models import talk, art
from discord.ext import commands
from discord import Embed
from random import choice


class Common(commands.Cog):
    def __init__(self, bot: commands.bot) -> None:
        self.bot = bot

    @commands.command(brief="Generates a random response.")
    async def ree(self, ctx):
        embed = Embed(description=talk.random_response())
        await ctx.send(embed=embed)

    @commands.command(brief="Shows pig art")
    async def art(self, ctx):
        for art_piece in art.PigArt.get_pig_art():
            await ctx.send(art_piece)

    @commands.command(brief="Get a random pig art piece to brighten your day")
    async def random_pig(self, ctx):
        await ctx.send(choice(art.PigArt.get_pig_art()))
