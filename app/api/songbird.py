import logging
import os
import sys
import uuid

from discord import slash_command, option, PCMVolumeTransformer, FFmpegPCMAudio, Bot
import asyncio
from discord.ext import commands
from models import config
from songbirdcore import youtube

logger = logging.getLogger(__name__)


class Songbird(commands.Cog):
    def __init__(self, config: config.PigBotSettings, bot: Bot) -> None:
        logger.info(f"initializing songbird api")
        self.bot = bot
        self.queue = []
        self.downloads_folder = os.path.join(sys.path[0], "downloads")
        self.config = config
        if not os.path.exists(self.downloads_folder):
            os.mkdir(self.downloads_folder)
        logger.info(f"songbird api initialed: downloads will be saved in '{self.downloads_folder}'")

    @slash_command()
    @option(
        "url",
        description="url of song to play",
        type=str,
    )
    async def play(self, ctx, url: str):
        logger.info(f"received play command for '{url}'")

        if ctx.voice_client is None:
            if ctx.author.voice:  # pyright: ignore
                await ctx.author.voice.channel.connect()  # pyright: ignore
            else:
                await ctx.respond("You must be connected to a voice channel to use 'play'.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():  # pyright: ignore
            ctx.voice_client.stop()  # pyright: ignore
        
        await ctx.defer()
        song_name = str(uuid.uuid4())
        song_path = os.path.join(self.downloads_folder, song_name)
        loop = self.bot.loop or asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: youtube.run_download(
                url=url, file_path_no_format=song_path, file_format="mp3"
            ),
        )
        # Gets voice channel of message author
        source = PCMVolumeTransformer(
            FFmpegPCMAudio(f"{song_path}.mp3")
        )
        ctx.voice_client.play(
            source, after=lambda e: logger.error("error playing song") if e else None
        )
        # Sleep while audio is playing.
        await ctx.followup.send(f"now playing: {url}")
        logger.info(f"play command for '{url}' ran successfully")

    @slash_command(description="stop the currently playing song")
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        logger.info(f"received stop command")
        if ctx.voice_client is None:
            return await ctx.respond("You must be connected to a voice channel.")
        await ctx.defer()
        await ctx.voice_client.disconnect(force=True)  # pyright: ignore
        await ctx.followup.send("roger")
        logger.info(f"stop command successful.")

    @slash_command(description="change volume")
    @option(
        "volume",
        type=int,
        description="enter an integer, as loud as you want?"
    )
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""
        logger.info(f"received volume command for volume={volume}")
        if ctx.voice_client is None:
            return await ctx.respond("You must be connected to a voice channel.")
        await ctx.defer()
        ctx.voice_client.source.volume = volume / 100  # pyright: ignore
        await ctx.followup.send(f"Changed volume to {volume}%")
        logger.info(f"volume command issued successfully")

