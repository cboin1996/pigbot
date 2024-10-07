import asyncio
import enum
import glob
import json
import logging
import os
import re
import sys
from typing import Dict, Optional

import pydantic
import requests
from bs4 import BeautifulSoup
from discord import (
    AutocompleteContext,
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
from util import trie

logger = logging.getLogger(__name__)

SONG_MATCH_SPLIT_KEY = "--> "


class YoutubeMeta(pydantic.BaseModel):
    url: str
    file_path: str
    # set title via best-effort.
    title: Optional[str]


class MetaDbManager:

    def __init__(self, path: str):
        self.path = path
        self.trie = trie.Trie()

        # initialize metadata db
        if not os.path.exists(path):
            with open(path, "w") as f:
                json.dump({}, f)
                self.db = {}

        # ingest metadb into trie for rapid memory lookup of song names
        # and associated metadb keys
        self.load()

    def write(self) -> bool:
        try:
            with open(self.path, "w") as f:
                json.dump(self.db, f)
                logger.info(f"wrote meta db '{self.path}'")
                return True
        except Exception as e:
            logger.exception(f"error while writing metadata to {self.path}", e)
            return False

    def load(self) -> bool:
        try:
            with open(self.path, "r") as f:
                self.db = json.load(f)
                logger.info(f"loaded meta db '{self.path}'")

            for id, item in self.db.items():
                parsed_item = YoutubeMeta.model_validate(item)
                if parsed_item.title:
                    self.trie.insert(parsed_item.title, terminator=id)
                else:
                    logger.info(
                        f"skipping insertion of song w/ url {item.url} as no title exists for it within meta db."
                    )
            logger.info(f"trie constructed successfully")
            return True

        except Exception as e:
            logger.exception(f"error while initializing metadatadb: ", e)
            return False

    def get_song_meta(self, id: str) -> Optional[YoutubeMeta]:
        """retrieve song metadata given an id, and song provider
        Args:
            song_provider (MetaDbSongProviders): the song provider
            id (str): the id of the song

        Returns (dict): song metadata
        """
        item = self.db.get(id, None)
        if not item:
            logger.error(f"no item in meta db for id: {id}")
            return None
        try:
            return YoutubeMeta.model_validate(item)
        except pydantic.ValidationError as e:
            logger.exception(f"could not parse metadata item: {item}", e)
            return None

    def add_song_meta(self, id: str, song_meta: YoutubeMeta) -> bool:
        # update meta db
        self.db[id] = song_meta.model_dump()
        # update trie if title exists for song
        if song_meta.title:
            self.trie.insert(song_meta.title, terminator=id)
        return self.write()


async def _get_url_from_title(ctx: AutocompleteContext):
    db_lock = ctx.cog.meta_db_lock  # pyright: ignore
    db = ctx.cog.meta_db  # pyright: ignore
    trie = ctx.cog.meta_db.trie  # pyright: ignore
    output_to_user = []
    try:
        async with db_lock:
            if ctx.value == "":
                trie_matches = trie.list_keys(trie.root)
            else:
                trie_matches = trie.starts_with(ctx.value)  # pyright: ignore

        # must recieve trie matches and their terminators,
        # which correspond to watch ids
        if not trie_matches:
            logger.info(f"no matches from trie for query: {ctx.value}")
            return []

        logger.info(f"recieved matches from trie: {trie_matches}")
        # load matching data from meta_db
        # for each match from the trie
        # retrieve the termination value -- which is the watch id

        for match in trie_matches:
            async with db_lock:
                # search in trie takes iterations O(k)
                # where k is length of match
                match_terminators = trie.search(match)

            # perform constant lookup for each terminator,
            # and add result to output
            for terminator in match_terminators:
                async with db_lock:
                    song_meta = db.get_song_meta(terminator)
                output_to_user.append(
                    f"{song_meta.url}{SONG_MATCH_SPLIT_KEY}{song_meta.title}"[:97]
                    + "..."
                )
                logger.info(f"output to user = {output_to_user}")

        return output_to_user
    except Exception as e:
        logger.exception(f"error while attempting autocomplete: ", e)
        return []


class Songbird(commands.Cog):
    def __init__(self, config: config.PigBotSettings, bot: Bot) -> None:
        logger.info(f"initializing songbird api")
        self.bot = bot
        self.queue_lock = asyncio.Lock()
        self.queue = []
        self.downloads_folder = os.path.join(sys.path[0], "downloads")
        self.config = config
        self.song_format = "mp3"
        self.meta_db = MetaDbManager(
            path=os.path.join(sys.path[0], "downloads", "metadb.json")
        )
        self.meta_db_lock = asyncio.Lock()

        if not os.path.exists(self.downloads_folder):
            os.mkdir(self.downloads_folder)
        logger.info(
            f"songbird api initialized: downloads will be saved in '{self.downloads_folder}'"
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

    def _get_video_title(self, url: str) -> Optional[str]:
        try:
            r = requests.get(url)
            soup = BeautifulSoup(r.text, "html.parser")
            link = soup.find_all(name="title")[0]
            return link.text

        except Exception as e:
            logger.exception(
                f"could not get title for video '{url}'. Continuing without", e
            )
            return None

    async def get_song(self, url: str) -> Optional[str]:
        """downloads a song from youtube if not on disk,
        otherwise returns song from disk

        Args:
            url (str): the url to download
            song_path (str): the name of the file to save the download to, excluding extension

        Returns:
            the file-path to the song, otherwise None if error occured.
        """
        id = self._get_video_id(url)
        song_path = os.path.join(self.downloads_folder, id)
        # query metadata db
        async with self.meta_db_lock:
            song_meta = self.meta_db.get_song_meta(id)

        if song_meta:
            return song_meta.file_path

        # allow concurrent downloads
        # since songbird is blocking
        loop = self.bot.loop or asyncio.get_event_loop()
        result_path = await loop.run_in_executor(
            None,
            lambda: youtube.run_download(
                url=url, file_path_no_format=song_path, file_format=self.song_format
            ),
        )
        if not result_path:
            return None
        # add song meta to db
        async with self.meta_db_lock:
            success = self.meta_db.add_song_meta(
                id=id,
                song_meta=YoutubeMeta(
                    url=url, title=self._get_video_title(url), file_path=result_path
                ),
            )
            if not success:
                return None
        return result_path

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
        fut = asyncio.run_coroutine_threadsafe(self.get_song(url), loop)
        song_path = fut.result()
        if not song_path:
            msg = f"An error occured while trying to obtain a song for url '{url}'."
            logger.error(msg)
            return asyncio.run_coroutine_threadsafe(ctx.followup.send(msg), loop)
        # assert before playing that another song isn't playing.
        if ctx.voice_client.is_playing():
            asyncio.run_coroutine_threadsafe(self.enqueue(ctx.followup.send, url), loop)
        source = PCMVolumeTransformer(FFmpegPCMAudio(song_path))
        ctx.voice_client.play(source, after=lambda e: self._play_next(ctx))
        asyncio.run_coroutine_threadsafe(
            ctx.followup.send(f"Playing: {url}."),
            loop,
        )

    async def enqueue(self, response_func, url: str = ""):
        if url != "":
            async with self.queue_lock:
                self.queue.append(url)
            msg = f"added '{url}' to queue.. queue length is '{len(self.queue)}'"
            logger.info(msg)
            return await response_func(
                embed=Embed(
                    title=f"Added '{url}' to queue:\n", description=self.render_queue()
                )
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

        if ctx.voice_client.is_playing():  # pyright: ignore
            # queue song if url provided
            await self.enqueue(ctx.respond, url)
            return

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

        song_path = await self.get_song(url)
        if not song_path:
            msg = f"An error occured while trying to obtain a song for url '{url}'."
            logger.error(msg)
            return ctx.followup.send(msg)

        # assert before playing that another song isn't playing.
        if ctx.voice_client.is_playing():
            return await self.enqueue(ctx.followup.send, url)
        source = PCMVolumeTransformer(FFmpegPCMAudio(song_path))
        ctx.voice_client.play(source, after=lambda e: self._play_next(ctx))
        await ctx.followup.send(f"Playing: {url}.")

    @slash_command(description="play a song. add's song to queue if already playing")
    @option(
        "url",
        type=str,
        description="url of song to play. If unspecified, next song in queue is played.",
    )
    @option("search", type=str, autocomplete=_get_url_from_title)
    async def play(self, ctx, url: str = "", search: str = ""):
        logger.info(f"received play command: url='{url}', search='{search}'")
        if url != "":
            await self._play(ctx, url)
        if search != "":
            await self._play(ctx, search.split(SONG_MATCH_SPLIT_KEY)[0])

    @slash_command(description="skip current song.")
    async def next(self, ctx):
        logger.info(f"received next command")
        if ctx.voice_client is None:
            return await ctx.respond("I am not connected to a voice channel..")
        if ctx.voice_client.is_playing():
            logger.info(f"stopping current song")
            await ctx.respond("skipping current song!")
            return ctx.voice_client.stop()
        else:
            return await ctx.respond(
                "Uh-uh-uh.. I can't skip a song if there isn't one playing"
            )

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
        else:
            await ctx.respond("nothing to resume.")

    @slash_command(description="resume the current song")
    async def pause(self, ctx):
        """pause the current song"""
        logger.info(f"received pause command")
        if ctx.voice_client is None:
            return await ctx.respond("I am not connected to a voice channel..")

        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.respond("pausing")
        else:
            await ctx.respond("nothing to pause :(")

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

            await ctx.respond(msg)
