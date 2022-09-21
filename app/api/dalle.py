from argparse import ArgumentParser, ArgumentError
import logging
from typing import List, Optional, Dict, Union
import sys
import asyncio

from discord.ext import tasks, commands
from models import config
import requests
from pydantic import BaseModel
from discord import Embed, File, Member
import shlex
import io
import aiohttp
import os
from discord.commands.context import ApplicationContext
from discord.types.threads import Thread
from discord import slash_command, option
from discord import AutocompleteContext
import asyncio

from .common import (
    get_ip,
    send_chunked_messaged,
    send_not_httpok_msg,
    send_generic_error_msg,
    get_context_or_thread_for_message,
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


class ImageSearchResponse(BaseModel):
    images: List[str] = []


class ImageSearchParams:
    """Implemented as a custom class since aiohttp is strict on query parameter formatting."""

    search_param: str
    starts_with: str

    def __init__(self, search_param: str, starts_with: str):
        self.search_param = search_param
        self.starts_with = str(starts_with).lower()  # aiohttp wants str bools.


async def get_image_list_autocomplete(ctx: AutocompleteContext):
    """Callback for image search autocomplete"""
    async with ctx.cog.images_lock:
        images = dict(ctx.cog.images)
    return [image for image in images if ctx.value.lower() in image]


class Dalle(commands.Cog):
    def __init__(
        self, config: config.PigBotSettings, bot: commands.bot, ip: str, port: int
    ):
        self.bot = bot
        self.ip = ip
        self.port = port
        self.url = f"http://{self.ip}:{self.port}/dalle"
        self.config = config
        self.images: Dict[
            str, str
        ] = {}  # will store truncated image paths and the matching full path
        self.images_lock = asyncio.Lock()
        self.image_list_gatherer.start()

    @slash_command(
        description="The main inference command for generating images from dalle given a query",
    )
    @option("query", description="what to generate the images from", type=str)
    @option(
        "number_of_images",
        description="the number of images to generate",
        required=False,
        type=int,
        default=2,
    )
    @option(
        "dalle_sha",
        description="the dalle-mini model sha",
        required=False,
        type=str,
        default="",
    )
    @option(
        "vqgan_sha", description="vqgan model sha", required=False, type=str, default=""
    )
    async def dalle_see(
        self,
        ctx,
        query: str,
        number_of_images: int = 2,
        dalle_sha: str = "",
        vqgan_sha: str = "",
    ):
        """The main inference command for generating images from dalle given a query

        Args:
            ctx (_type_): _description_
            query (str): the query to generate the image from
            number_of_images (int, optional): the number of images to generate. Defaults to 2.
            dalle_sha (str, optional): the dalle-mini sha to use for inference. Defaults to "".
            vqgan_sha (str, optional): the vqgan sha to use for inference. Defaults to "".
        """
        cm = ctx.command
        interaction = await ctx.respond(f"Received {ctx.command.name}")
        queries = [query]
        ctx_or_thread = await get_context_or_thread_for_message(
            ctx,
            thread_name=str(queries),
            i_message=await interaction.original_message(),
        )
        if number_of_images > self.config.pigbot_dalle_max_number_of_images:
            await ctx_or_thread.send(
                embed=Embed(
                    title=f"Invalid argument!",
                    description=f"number_of_images={number_of_images} must be within [0,{self.config.pigbot_dalle_max_number_of_images}]!",
                )
            )
            return
        # obtain model paths from server
        model_paths = await self.get_dalle_browse(ctx_or_thread, dalle_sha, vqgan_sha)

        if model_paths is None:
            return

        if not model_paths:
            await ctx_or_thread.send(
                embed=Embed(
                    title=f"Looks like theres no models downloaded yet! Try $dalle_pull to get some on the server"
                )
            )
            return

        message = await ctx_or_thread.send(
            embed=Embed(
                title=f"Submitting query to dalle-ays: {queries}",
                description=f"Using models: {model_paths}",
            )
        )
        image_paths_obj = await self.post_model_show(
            ctx_or_thread,
            model_paths,
            queries,
            number_of_images,
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
                await ctx_or_thread.send(
                    file=File(data, filename=image_name), embed=embed
                )

    @slash_command(description="tell dalle-ays to display an image")
    @option(
        "image_path",
        description="path to the image you want to see",
        type=str,
        autocomplete=get_image_list_autocomplete,
    )
    async def dalle_image(self, ctx, image_path: str):
        """Show a image given a path.

        Args:
            image_path (str): the path to the image on the backends disk
        """
        await ctx.respond(f"Received {ctx.command.name}")
        async with self.images_lock:
            if (
                image_path in self.images
            ):  # transform truncated paths back to full paths if they exist
                image_path = self.images[image_path]
        data = await self.get_image(ctx, image_path)
        if data is None:
            return
        image_name = os.path.basename(image_path)
        embed = Embed(title=image_name)
        embed.set_image(url=f"attachment://{image_name}")
        await ctx.send(file=File(data, filename=image_name), embed=embed)

    @slash_command(description="search up some images on disk!")
    @option(
        "query",
        description="the keyword you want to find images matching",
        required=False,
        type=str,
        default="",
    )
    @option(
        "display",
        description="Choosing True displays images, False displays image paths",
        required=False,
        type=bool,
        default=True,
    )
    @option(
        "startswith",
        description="Choosing True searchs from the start of image names, False searches anywhere.",
        required=False,
        type=bool,
        default=False,
    )
    @option(
        "num_matches",
        description="The number of images to return",
        required=False,
        type=int,
        default=2,
    )
    async def dalle_images(
        self,
        ctx,
        query: str = "",
        display: bool = True,
        startswith: bool = False,
        num_matches: int = 3,
    ):
        """search for images on disk

        Args:
            query (str, optional): Image name to search for. Defaults to "".
            display (bool, optional): Whether to display images or image paths. Defaults to True.
            startswith (bool, optional): True conducts a startswith search, false matches substrings. Defaults to False.
            num_matches (int, optional): The number of search matches to return. Defaults to 3.
        """
        dkds = ctx
        interaction = await ctx.respond(f"Received {ctx.command.name}")
        ctx_or_thread = await get_context_or_thread_for_message(
            ctx,
            thread_name=f"{ctx.command.name}: {query}",
            archive_duration=60,
            i_message=await interaction.original_message(),
        )

        if num_matches > 3 or num_matches <= 0:
            ctx_or_thread.send(
                "The allowed number of image matches falls within [1,3]!"
            )

        # get image list based on search cli
        image_search_object = await self.get_image_list(
            ctx_or_thread,
            query_params=ImageSearchParams(search_param=query, starts_with=startswith),
        )
        if image_search_object is None:
            return
        # display images
        if display:
            for i, image_path in enumerate(image_search_object.images):
                if i >= num_matches:
                    return

                data = await self.get_image(ctx, image_path)
                image_name = os.path.basename(image_path)
                embed = Embed(title=image_name, description=image_path)
                embed.set_image(url=f"attachment://{image_name}")
                await ctx_or_thread.send(
                    file=File(data, filename=image_name), embed=embed
                )
        else:  # display text
            # we are limited to 4000 characters in embed description, so we will
            # break it up here
            await send_chunked_messaged(
                ctx_or_thread,
                "Here the images on disk for dalle-ays: ",
                "\n".join(image_search_object.images),
                4000,
            )

    @slash_command(description="tell dalle to pull a model")
    @option(
        "dalle_sha",
        description="the dalle-mini model sha",
        required=False,
        type=str,
        default="",
    )
    @option(
        "vqgan_sha", description="vqgan model sha", required=False, type=str, default=""
    )
    async def dalle_pull(self, ctx, dalle_sha: str = "", vqgan: str = ""):
        """Pulls models to disk

        Args:
            dalle_sha (str, optional): The dalle-mini model sha to pull. Defaults to "".
            vqgan (str, optional): the jax vqgan sha to pull. Defaults to "".
        """
        await ctx.respond(f"Received {ctx.command.name}")
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

    @slash_command(description="Check to see if a model exists on disk!")
    @option(
        "dalle_sha",
        description="the dalle-mini model sha",
        required=False,
        type=str,
        default="",
    )
    @option(
        "vqgan_sha", description="vqgan model sha", required=False, type=str, default=""
    )
    async def dalle_browse(self, ctx, dalle_sha: str = "", vqgan_sha: str = ""):
        """Browse the current model that the backend is using.

        Args:
            dalle_sha (str, optional): The dalle-mini sha to check for. Defaults to "".
            vqgan_sha (str, optional): The vqgan sha to check for. Defaults to "".
        """
        await ctx.respond(f"Received {ctx.command.name}")
        model_paths = await self.get_dalle_browse(ctx, dalle_sha, vqgan_sha)
        if model_paths is None:
            return
        elif not model_paths:
            await ctx.respond(
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

    @tasks.loop(seconds=30)
    async def image_list_gatherer(self):
        """Keep image list in memory for more efficient autocomplete search"""
        endpoint = f"{self.url}" + "/images"
        try:
            json_query_params = ImageSearchParams(
                search_param="", starts_with=False
            ).__dict__
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=json_query_params) as response:
                    if response.status != 200:
                        title = f"Error from server at {endpoint}"
                        description = f"Url = {response.url}, \nCode={response.status}, \nBody={await response.json()}"
                        logger.exception(
                            f"Error from server at {endpoint}. \n Code={response.status}, \n Body={title} \n{description}"
                        )
                        return
                    images = ImageSearchResponse.parse_obj(await response.json()).images
                    images_dict = {image[:100].lower(): image for image in images}
                    async with self.images_lock:
                        self.images = images_dict  # discord requires truncated list

        except Exception as e:
            logger.exception(
                f"Error performing request against endpoint {endpoint}: {e}"
            )

    async def get_dalle_browse(
        self,
        ctx_or_thread: Union[ApplicationContext, Thread],
        dalle_sha: str = "",
        vqgan_sha: str = "",
    ) -> Optional[ModelPaths]:
        """Helper function for getting model paths from dalle-ays

        Returns:
            Optional[ModelPaths]: paths on the server to the models
        """
        model_paths = None
        endpoint = self.url + "/browse"
        query_params = None
        if dalle_sha != "" or vqgan_sha != "":
            query_params = {"dalle_sha": dalle_sha, "vqgan_sha": vqgan_sha}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=query_params) as response:
                    if response.status != 200:
                        await send_not_httpok_msg(ctx_or_thread, endpoint, response)
                        return

                    return ModelPaths.parse_obj(await response.json())
        except Exception as e:
            await send_generic_error_msg(ctx_or_thread, endpoint, e)

    async def post_model_show(
        self,
        ctx_or_thread: Union[ApplicationContext, Thread],
        model_paths: ModelPaths,
        queries: List[str],
        n_predictions=int,
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
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload.dict()) as response:
                    if response.status != 200:
                        await send_not_httpok_msg(ctx_or_thread, endpoint, response)
                        return
                    else:
                        return ImagePathResponse.parse_obj(await response.json())

        except Exception as e:
            await send_generic_error_msg(ctx_or_thread, endpoint, e)

    async def get_pull(
        self, ctx_or_thread: Union[ApplicationContext, Thread]
    ) -> Optional[ModelPaths]:
        """Helper for performing a get request to dalle-ays /pull endpoint."""
        endpoint = f"{self.url}" + "/pull"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint) as response:
                    if response.status != 200:
                        await send_not_httpok_msg(ctx_or_thread, endpoint, response)
                        return

                    return ModelPaths.parse_obj(await response.json())

        except Exception as e:
            await send_generic_error_msg(ctx_or_thread, endpoint, e)

    async def get_image_list(
        self,
        ctx_or_thread: Union[ApplicationContext, Thread],
        query_params: ImageSearchParams,
    ) -> Optional[ImageSearchResponse]:
        """Helper for listing images"""
        endpoint = f"{self.url}" + "/images"
        try:
            json_query_params = query_params.__dict__
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, params=json_query_params) as response:
                    if response.status != 200:
                        await send_not_httpok_msg(ctx_or_thread, endpoint, response)
                        return

                    return ImageSearchResponse.parse_obj(await response.json())
        except Exception as e:
            await send_generic_error_msg(ctx_or_thread, endpoint, e)

    async def get_image(
        self, ctx_or_thread: Union[ApplicationContext, Thread], image_path: str
    ) -> Optional[io.BytesIO]:
        """Helper for getting an image"""
        endpoint = f"{self.url}" + f"/image?image_path={image_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint) as response:
                if response.status != 200:
                    await send_not_httpok_msg(ctx_or_thread, endpoint, response)
                    return
                data = io.BytesIO(await response.read())
                return data
