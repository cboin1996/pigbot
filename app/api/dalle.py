from argparse import ArgumentParser, ArgumentError
import logging
from typing import List, Optional, Dict
import sys

from discord.ext import tasks, commands
from models import config
import requests
from pydantic import BaseModel
from discord import Embed, File
import shlex
import io
import aiohttp
import os

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
            choices=range(1, 4),
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
        model_paths = await self.get_dalle_browse(ctx)
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
        await ctx.send(
            embed=Embed(
                title="Here the images on disk for dalle-ays: ",
                description="\n".join(lyst),
            )
        )

    @commands.command(brief="tell dalle to pull a model")
    async def dalle_pull(self, ctx):
        await ctx.send(embed=Embed(title="Pull initiated!"))
        model_paths = await self.get_pull(ctx)
        if model_paths is None:
            return
        if not model_paths:
            await ctx.send(
                embed=Embed(
                    title="Dalle-ays has models available on disk!",
                    description=model_paths,
                )
            )

    @commands.command(brief="see whats under the hood!")
    async def dalle_browse(self, ctx):
        model_paths = await self.get_dalle_browse(ctx)
        if model_paths is None:
            return
        elif model_paths == False:
            await ctx.send(
                embed=Embed(
                    title=f"Looks like theres no models downloaded yet! Try using $pull to get the latest!"
                )
            )
        else:
            embed = Embed(
                title="It appears there are models on disk!", description=model_paths
            )
            await ctx.send(embed=embed)

    async def get_dalle_browse(self, ctx) -> Optional[ModelPaths]:
        """Helper function for getting model paths from dalle-ays

        Returns:
            Optional[ModelPaths]: paths on the server to the models
        """
        model_paths = None
        endpoint = self.url + "/browse"
        try:
            response = requests.get(endpoint)
            if response.status_code != 200:
                send_not_httpok_msg(self, ctx, endpoint, response)
            model_paths = ModelPaths.parse_obj(response.json())
        except Exception as e:
            await self.send_generic_error_msg(ctx, endpoint, e)

        return model_paths

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
            response = requests.post(endpoint, data=payload.json())
            if response.status_code != 200:
                send_not_httpok_msg(self, ctx, endpoint, response)
            else:
                return ImagePathResponse.parse_obj(response.json())

        except Exception as e:
            await self.send_generic_error_msg(ctx, endpoint, e)

    async def get_pull(self, ctx) -> Optional[ModelPaths]:
        """Helper for performing a get request to dalle-ays /pull endpoint."""
        endpoint = f"{self.url}" + "/pull"
        try:
            response = requests.get(endpoint)
            if response.status_code != 200:
                send_not_httpok_msg(self, ctx, endpoint, response)
            model_paths = ModelPaths.parse_obj(response.json())
            if model_paths:
                return model_paths

        except Exception as e:
            await self.send_generic_error_msg(ctx, endpoint, e)

    async def get_image_list(self, ctx) -> List[str]:
        """Helper for listing images"""
        endpoint = f"{self.url}" + "/images"
        try:
            response = requests.get(endpoint)
            if response.status_code != 200:
                send_not_httpok_msg(self, ctx, endpoint, response)
            return response.json()
        except Exception as e:
            await self.send_generic_error_msg(ctx, endpoint, e)

    async def get_images(self, ctx, image_path: List[str]):
        """Helper for getting images"""

    async def get_image(self, ctx, image_path: str) -> io.BytesIO:
        """Helper for getting an image"""
        endpoint = f"{self.url}" + f"/image?image_path={image_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint) as response:
                if response.status != 200:
                    return await self.send_generic_error_msg(ctx, endpoint, response)
                data = io.BytesIO(await response.read())
                return data

    async def send_not_httpok_msg(self, ctx, endpoint, response):
        logger.exception(
            f"Error from server at {endpoint}. \n Code={response.status_code}, \n Body={response.json()}"
        )
        return await ctx.send(
            embed=Embed(
                title=f"Error from server at {endpoint}",
                description=f"Code={response.status_code}, \nBody={response.json()}",
            )
        )

    async def send_generic_error_msg(self, ctx, endpoint: str, e: Exception()):
        logger.exception(f"Error trying to reach server at {endpoint}: {e}")
        return await ctx.send(
            embed=Embed(
                title=f"Error from server at {endpoint}",
                description=f"Exception occurred: {e}",
            )
        )
