import aiohttp
from discord import Embed, File
import datetime
from typing import List, Optional
import logging
from discord.commands.context import ApplicationContext
from discord.types.threads import Thread
from typing import Union

logger = logging.getLogger(__name__)
"""Common tools for use across the apis
"""


async def get_ip(bot, channels: List[str]) -> str:
    """Helper for getting ip from ip api"""
    endpoint = "https://api.ipify.org"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint) as response:
                if response.status != 200:
                    return await send_not_httpok_msg_to_channels(
                        bot, endpoint, channel_ids, await response
                    )

                byts = await response.read()
                return byts.decode("utf-8")

    except Exception as e:
        await send_generic_error_message_to_channels(bot, endpoint, channels, e)


async def has_ip_changed(bot, last_ip: str, channels: List[str]) -> bool:
    """Check ip to see if it is different from the given ip
    Return: None if the ip has changed, otherwise the new ip
    """
    current_ip = await get_ip(bot, channels)
    # check for error on requests.. should only execute if wifi is up or requests were good.
    if last_ip != None and current_ip != None:
        if last_ip != current_ip:
            return current_ip
        else:
            return None


async def send_not_httpok_msg(
    ctx_or_thread: Union[ApplicationContext, Thread], endpoint, response
):
    logger.exception(
        f"Error from server at {endpoint}. \n Code={response.status}, \n Body={await response.json()}"
    )
    return await ctx_or_thread.send(
        embed=Embed(
            title=f"Error from server at {endpoint}",
            description=f"Code={response.status}, \nBody={await response.json()}",
        )
    )


async def send_generic_error_msg(
    ctx_or_thread: Union[ApplicationContext, Thread], endpoint: str, e: Exception()
):
    logger.exception(f"Error performing request against endpoint {endpoint}: {e}")
    return await ctx_or_thread.send(
        embed=Embed(
            title=f"Error from server at {endpoint}",
            description=f"Exception occurred: {e}",
        )
    )


async def send_generic_error_message_to_channels(
    bot, endpoint: str, channel_ids: List[str], e: Exception()
):
    """Outputs message to given discord channels

    Args:
        channel_ids (List[str]): the list of discord channel ids
        msg (str): the message
    """
    logger.exception(f"Error performing request against endpoint {endpoint}: {e}")
    if channel_ids is not None:
        message_to_channels(
            bot,
            channel_ids,
            f"Error from server at {endpoint}",
            f"Exception occurred: {e}",
        )


async def send_not_httpok_msg_to_channels(
    bot, endpoint: str, channel_ids: List[str], response
):
    logger.exception(
        f"Error from server at {endpoint}. \n Code={response.status}, \n Body={await response.json()}"
    )
    if channel_ids is not None:
        message_to_channels(
            bot,
            channel_ids,
            f"Error from server at {endpoint}",
            f"Code={response.status}, \nBody={await response.json()}",
        )


async def send_chunked_messaged(
    ctx: Union[ApplicationContext, Thread], title: str, long_str: str, limit: int
):
    """Send a long message in multiple embeds

    Args:
        long_str (str): the long message
        limit (int): the character limit
    """
    length = len(long_str)
    idx = 0
    chunked_msgs = [long_str[i : i + limit] for i in range(0, len(long_str), limit)]
    for i, msg in enumerate(chunked_msgs):
        await ctx.send(
            embed=Embed(
                title=title + f" part {i+1} of {len(chunked_msgs)}", description=msg
            )
        )


async def message_to_channels(
    bot, channel_ids: List[str], msg: str, description: Optional[str] = ""
):
    """Outputs message to given discord channels

    Args:
        channel_ids (List[str]): the list of discord channel ids
        msg (str): the message
    """
    if channel_ids is not None:
        for channel_id in channel_ids:
            channel = bot.get_channel(int(channel_id))
            await channel.send(embed=Embed(title=msg, description=description))


async def get_context_or_thread_for_message(
    ctx: ApplicationContext,
    thread_name: Optional[str] = "",
    archive_duration: int = 1440,
) -> Union[ApplicationContext, Thread]:
    """Given the app context, generate a thread if possible and return the thread or app context.

    Args:
        ctx (ApplicationContext): _description_
        thread_name: Optional[str]:
        archive_duration: int archive duration for discord one of 1440, 60, 4320, 10080
    Returns:
        Union[ApplicationContext, Thread]: _description_
    """
    thread_name = ctx.message.content if thread_name == "" else thread_name
    if ctx.guild is not None:
        return await ctx.message.create_thread(
            name=thread_name, auto_archive_duration=archive_duration
        )
    else:
        return ctx
