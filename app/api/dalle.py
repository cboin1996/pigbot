from argparse import ArgumentParser, ArgumentError
import logging
from typing import List, Optional, Dict
import sys
import asyncio

from discord.ext import tasks, commands
from models import config
import requests
from pydantic import BaseModel
from discord import Embed, File
import shlex
import io
import aiohttp
import os

from .common import (
    get_ip,
    send_chunked_messaged,
    send_not_httpok_msg,
    send_generic_error_msg,
)

logger = logging.getLogger(__name__)


class ModelPaths(BaseModel):
    """Model for path structure that represents how
    dalle and its models are stored
    """

    dalle: str = ""
    vqgan: str = ""
    dalle_processor_tokenizer: str = ""
    dalle_processor_config: str = ""

    def __bool__(self):
        return (
            self.dalle != ""
            and self.vqgan != ""
            and self.dalle_processor_tokenizer != ""
            and self.dalle_processor_config != ""
        )

    def __hash__(self):
        return hash(
            (
                self.dalle,
                self.vqgan,
                self.dalle_processor_tokenizer,
                self.dalle_processor_config,
            )
        )

    def __eq__(self, other):
        return (
            self.dalle == other.dalle
            and self.vqgan == other.vqgan
            and self.dalle_processor_tokenizer == other.dalle_processor_tokenizer
            and self.dalle_processor_config == self.dalle_processor_config
        )


class QueryDalleBody(BaseModel):
    model_paths: ModelPaths
    queries: List[str]


class ImagePathResponse(BaseModel):
    prompts: Dict[str, List[str]] = {}


class Dalle(commands.Cog):
    def __init__(
        self, config: config.PigBotSettings, bot: commands.bot, ip: str, port: int
    ):
        self.bot = bot
        self.ip = ip
        self.port = port
        self.url = f"http://{self.ip}:{self.port}/dalle"

    @commands.command(
        brief="ask dalle to create something: -q phrase1 -n num_pics",
    )
    async def dalle_see(self, ctx, *, arg):
        # parse arguments from the user
        parser = ArgumentParser()
        parser.add_argument(
            "-q",
            dest="queries",
            action="append",
            help="input up to n queries for dalle. Ex. -q swag -q yolo",
        )
        parser.add_argument(
            "-n",
            dest="number_of_images",
            help="number of images to produce for each query",
            type=int,
            choices=range(1, 5),
        )
        parser.add_argument(
            "-dalle_sha",
            dest="dalle_sha",
            help="commit sha for the dalle-mini model (if none, uses dalle-ays defaults)",
            type=str,
            default="",
        )
        parser.add_argument(
            "-vqgan_sha",
            dest="vqgan_sha",
            help="commit sha for the vqgan model (if none, uses dalle-ays defaults)",
            type=str,
            default="",
        )
        try:
            parsed_args = parser.parse_args(shlex.split(arg))
        except ArgumentError as e:
            embed = Embed(
                title="You are using the cli incorrectly.", description=e.message
            )
            await ctx.send(embed=embed)
            return
        except SystemExit:  # we dont want to exit
            await ctx.send(
                embed=Embed(
                    title=f"You are using this cli option incorrectly",
                    description=f"{parser.format_help().replace('main.py', '$dalle_see')}",
                )
            )
            return

        # obtain model paths from server
        model_paths = await self.get_dalle_browse(ctx, parsed_args.dalle_sha, parsed_args.vqgan_sha)
        if model_paths is None:
            return

        if not model_paths:
            await ctx.send(
                embed=Embed(
                    title=f"Looks like theres no models downloaded yet! Try $dalle_pull to get some on the server"
                )
            )
            return

        await ctx.send(
            embed=Embed(
                title=f"Submitting query to dalle-ays: {parsed_args.queries}",
                description=f"Using models: {model_paths}",
            )
        )

        image_paths_obj = await self.post_model_show(
            ctx, model_paths, parsed_args.queries, parsed_args.number_of_images
        )
        if image_paths_obj is None:
            return

        # request images from server and post to discord chat :)

        for prompt, image_paths in image_paths_obj.prompts.items():
            for image_path in image_paths:
                data = await self.get_image(ctx, image_path)
                image_name = os.path.basename(image_path)
                embed = Embed(title=prompt, description=image_path)
                embed.set_image(url=f"attachment://{image_name}")
                await ctx.send(file=File(data, filename=image_name), embed=embed)

    @commands.command(brief="tell dalle-ays to display an image")
    async def dalle_image(self, ctx, *, image_path: str):
        data = await self.get_image(ctx, image_path)
        image_name = os.path.basename(image_path)
        embed = Embed(title=image_name)
        embed.set_image(url=f"attachment://{image_name}")
        await ctx.send(file=File(data, filename=image_name), embed=embed)

    @commands.command(brief="tell dalle-ays to show the images on disk")
    async def dalle_images(self, ctx):
        lyst = await self.get_image_list(ctx)
        # we are limited to 4000 characters in embed description, so we will
        # break it up here
        await send_chunked_messaged(
            ctx, "Here the images on disk for dalle-ays: ", "\n".join(lyst), 4000
        )

    @commands.command(brief="tell dalle to pull a model")
    async def dalle_pull(self, ctx):
        await ctx.send(embed=Embed(title="Pull initiated!"))
        model_paths = await self.get_pull(ctx)
        if model_paths is None:
            return
        if model_paths:
            await send_chunked_messaged(
                ctx,
                "It appears there are models on disk!",
                str(model_paths.json()),
                4000,
            )

    @commands.command(brief="see whats under the hood!")
    async def dalle_browse(self, ctx):
        model_paths = await self.get_dalle_browse(ctx)
        if model_paths is None:
            return
        elif not model_paths:
            await ctx.send(
                embed=Embed(
                    title=f"Looks like theres no models downloaded yet! Try using $pull to get the latest!"
                )
            )
        else:
            await send_chunked_messaged(
                ctx,
                "It appears there are models on disk!",
                str(model_paths.json()),
                4000,
            )

    async def get_dalle_browse(
        self, ctx, dalle_sha: str = "", vqgan_sha: str = ""
    ) -> Optional[ModelPaths]:
        """Helper function for getting model paths from dalle-ays

        Returns:
            Optional[ModelPaths]: paths on the server to the models
        """
        model_paths = None
        endpoint = self.url + "/browse"
        query_params = None
        if dalle_sha != "" and vqgan != "":
            query_params = {"dalle_sha": dalle_sha, "vqgan_sha": vqgan_sha}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=query_params) as response:
                    if response.status != 200:
                        return await send_not_httpok_msg(ctx, endpoint, response)

                    return ModelPaths.parse_obj(await response.json())
        except Exception as e:
            await send_generic_error_msg(ctx, endpoint, e)

    async def post_model_show(
        self, ctx, model_paths: ModelPaths, queries: List[str], n_predictions=int
    ) -> Optional[ImagePathResponse]:
        """Helper function for posting to dalle to request image generation

        Args:
            model_paths (ModelPaths): ModelPaths object
            queries (List[str]): list of queries for dalle to process

        Returns:
            Optional[ImagePathResponse]: the image path response from dalle-ays, or nothing if error occured!
        """
        # submit request to see images based on returned model
        endpoint = self.url + f"/show?n_predictions={n_predictions}"
        try:
            payload = QueryDalleBody(model_paths=model_paths, queries=queries)
            logger.info(payload.json())
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload.dict()):
                    if response.status != 200:
                        return await send_not_httpok_msg(ctx, endpoint, response)
                    else:
                        return ImagePathResponse.parse_obj(await response.json())

        except Exception as e:
            await send_generic_error_msg(ctx, endpoint, e)

    async def get_pull(self, ctx) -> Optional[ModelPaths]:
        """Helper for performing a get request to dalle-ays /pull endpoint."""
        endpoint = f"{self.url}" + "/pull"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint) as response:
                    if response.status != 200:
                        return await send_not_httpok_msg(ctx, endpoint, response)

                    return ModelPaths.parse_obj(await response.json())

        except Exception as e:
            await send_generic_error_msg(ctx, endpoint, e)

    async def get_image_list(self, ctx) -> List[str]:
        """Helper for listing images"""
        endpoint = f"{self.url}" + "/images"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint) as response:
                    if response.status != 200:
                        return await send_not_httpok_msg(ctx, endpoint, response)

                    return await response.json()
        except Exception as e:
            await send_generic_error_msg(ctx, endpoint, e)

    async def get_images(self, ctx, image_path: List[str]):
        """Helper for getting images"""

    async def get_image(self, ctx, image_path: str) -> io.BytesIO:
        """Helper for getting an image"""
        endpoint = f"{self.url}" + f"/image?image_path={image_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint) as response:
                if response.status != 200:
                    return await send_not_httpok_msg(ctx, endpoint, response)
                data = io.BytesIO(await response.read())
                return data