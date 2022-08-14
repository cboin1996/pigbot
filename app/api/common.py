import aiohttp
from discord import Embed, File
import datetime
from typing import List, Optional
import logging

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


async def send_not_httpok_msg(ctx, endpoint, response):
    logger.exception(
        f"Error from server at {endpoint}. \n Code={response.status}, \n Body={await response.json()}"
    )
    return await ctx.send(
        embed=Embed(
            title=f"Error from server at {endpoint}",
            description=f"Code={response.status}, \nBody={await response.json()}",
        )
    )


async def send_generic_error_msg(ctx, endpoint: str, e: Exception()):
    logger.exception(f"Error performing request against endpoint {endpoint}: {e}")
    return await ctx.send(
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


async def send_chunked_messaged(ctx, title: str, long_str: str, limit: int):
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
