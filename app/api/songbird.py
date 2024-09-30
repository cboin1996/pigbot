import asyncio
import glob
import logging
import os
import sys
import re
from typing import Optional

from discord import (
    Bot,
    Embed,
    FFmpegPCMAudio,
    PCMVolumeTransformer,
    option,
    slash_command,
)
from discord.ext import commands
from discord.utils import get
from models import config
from songbirdcore import youtube

logger = logging.getLogger(__name__)


class Songbird(commands.Cog):
    def __init__(self, config: config.PigBotSettings, bot: Bot) -> None:
        logger.info(f"initializing songbird api")
        self.bot = bot
        self.queue_lock = asyncio.Lock()
        self.queue = []
        self.downloads_folder = os.path.join(sys.path[0], "downloads")
        self.config = config
        self.song_format = "mp3"
        if not os.path.exists(self.downloads_folder):
            os.mkdir(self.downloads_folder)
        logger.info(
            f"songbird api initialed: downloads will be saved in '{self.downloads_folder}'"
        )

    def render_queue(self) -> str:
        """render the queue as a formatted str"""
        if len(self.queue) == 0:
            return ""
        message = ""
        for i, item in enumerate(self.queue):
            message += f"{i}. {item}\n"

        return message

    @slash_command(description="resets the song queue")
    async def reset(self, ctx):
        async with self.queue_lock:
            self.queue.clear()
        await ctx.respond(f"reset queue successfully")

    def _find_song(self, watch_id) -> Optional[str]:
        """finds song matching the watch_id on disk, returning the file path.
        If no song is found, return None
        """
        songs = glob.glob(os.path.join(self.downloads_folder, f"*.{self.song_format}"))
        for song in songs:
            if watch_id in song:
                logger.info(f"watch_id={watch_id} found on disk: {song}")
                return song.replace(f".{self.song_format}", "")

    def _get_video_id(self, url: str) -> str:
        pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
        regex = re.compile(pattern)
        results = regex.search(url)
        if not results:
            raise ValueError(f"No match for regex pattern {pattern} within {url}.")
        return results.group(1)

    def _play_next(self, ctx):
        """synchronous callback for playing next songs in queue."""
        loop = self.bot.loop or asyncio.get_event_loop()
        vc = get(self.bot.voice_clients, guild=ctx.guild)
        if len(self.queue) == 0:
            return asyncio.run_coroutine_threadsafe(
                ctx.followup.send(
                    f"No songs left in queue. Add songs with '/play', providing a url!"
                ),
                loop,
            )

        url = self.queue.pop(0)
        # check if song is on disk
        watch_id = self._get_video_id(url)
        song_path = self._find_song(watch_id)
        if not song_path:
            song_path = os.path.join(self.downloads_folder, watch_id)
            youtube.run_download(
                url=url, file_path_no_format=song_path, file_format=self.song_format
            )
        source = PCMVolumeTransformer(FFmpegPCMAudio(f"{song_path}.{self.song_format}"))
        ctx.voice_client.play(source, after=lambda e: self._play_next(ctx))
        asyncio.run_coroutine_threadsafe(
            ctx.followup.send(
                f"Playing: {url}."
            ),
            loop,
        )
    
    async def _play(self, ctx, url: str = ""):
        """routes play command to various tasks."""
        # base condition
        if ctx.voice_client is None:
            if ctx.author.voice:  # pyright: ignore
                await ctx.author.voice.channel.connect()  # pyright: ignore
            else:
                await ctx.respond(
                    "You must be connected to a voice channel to use 'play'."
                )
                raise commands.CommandError("Author not connected to a voice channel.")

        # queue song
        if ctx.voice_client.is_playing():  # pyright: ignore
            async with self.queue_lock:
                self.queue.append(url)
            msg = f"added '{url}' to queue.. queue length is '{len(self.queue)}'"
            logger.info(msg)
            return await ctx.respond(
                embed=Embed(
                    title=f"Added '{url}' to queue:\n", description=self.render_queue()
                )
            )

        # ctx.defer expects followup
        await ctx.defer()

        # check if song is in queue if no url provided
        if url == "":
            if len(self.queue) == 0:
                msg = (
                    f"no songs in queue. please use 'play', providing a url to add one"
                )
                logger.info(msg)
                return await ctx.respond(msg)
            async with self.queue_lock:
                url = self.queue.pop(0)

        # check if song is on disk
        watch_id = self._get_video_id(url)
        song_path = self._find_song(watch_id)
        if not song_path:
            song_path = os.path.join(self.downloads_folder, watch_id)
            loop = self.bot.loop or asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: youtube.run_download(
                    url=url, file_path_no_format=song_path, file_format=self.song_format
                ),
            )
        source = PCMVolumeTransformer(FFmpegPCMAudio(f"{song_path}.{self.song_format}"))
        ctx.voice_client.play(source, after=lambda e: self._play_next(ctx))
        await ctx.followup.send(
            f"Playing: {url}."
        )

    @slash_command(description="play a song. add's song to queue if already playing")
    @option(
        "url",
        type=str,
        description="url of song to play. If unspecified, next song in queue is played.",
    )
    async def play(self, ctx, url: str = ""):
        logger.info(f"received play command, url='{url}'")
        await self._play(ctx, url)

    @slash_command(description="skip current song.")
    async def next(self, ctx):
        logger.info(f"received next command")
        if ctx.voice_client is None:
            return await ctx.respond("I am not connected to a voice channel..")
        if ctx.voice_client.is_playing():
            logger.info(f"stopping current song")
            ctx.voice_client.stop()
            return await ctx.respond("skipping current song!")

    @slash_command(
        description="disconnect pigbot from the voice channel, quitting the current song."
    )
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        logger.info(f"received stop command")
        if ctx.voice_client is None:
            return await ctx.respond("I am not connected to a voice channel..")
        await ctx.defer()
        await ctx.voice_client.disconnect(force=True)  # pyright: ignore
        await ctx.followup.send("roger")

    @slash_command(description="resume the current song")
    async def resume(self, ctx):
        """resume's the current song"""
        logger.info(f"received resume command")
        if ctx.voice_client is None:
            return await ctx.respond("I am not connected to a voice channel..")

        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.respond("resuming")

    @slash_command(description="resume the current song")
    async def pause(self, ctx):
        """pause the current song"""
        logger.info(f"received pause command")
        if ctx.voice_client is None:
            return await ctx.respond("I am not connected to a voice channel..")

        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.respond("pausing")

    @slash_command(description="change volume")
    @option("volume", type=int, description="enter an integer, as loud as you want?")
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""
        logger.info(f"received volume command for volume={volume}")
        if ctx.voice_client is None:
            return await ctx.respond("I am not connected to a voice channel..")

        await ctx.defer()
        ctx.voice_client.source.volume = volume / 100  # pyright: ignore
        await ctx.followup.send(f"Changed volume to {volume}%")

    @slash_command(description="List the contents of the queue")
    async def list(self, ctx):
        """list the contents of the queue"""
        async with self.queue_lock:
            if len(self.queue) > 0:
                msg = f"View the queue contents below: \n\n{self.render_queue()}"
            else:
                msg = f"Queue is empty"

            await ctx.respond(
                msg 
            )
