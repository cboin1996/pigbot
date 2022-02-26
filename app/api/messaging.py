from models import talk
from discord.ext import commands
from discord import Embed

class Common(commands.Cog):
    def __init__(self, bot: commands.bot) -> None:
        self.bot = bot

    @commands.command(
        brief="Generates a random response."
    )
    async def ree(self, ctx):      
        embed = Embed(description=talk.random_response())
        await ctx.send(embed=embed)