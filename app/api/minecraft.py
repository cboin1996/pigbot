from typing import List, Optional
from mcstatus import JavaServer
from discord.ext import tasks, commands
from discord import Embed
import logging
from models import config
import asyncio
from .common import has_ip_changed, message_to_channels, update_channel_topics

from discord import slash_command

logger = logging.getLogger(__name__)


class Minecraft(commands.Cog):
    def __init__(
        self, config: config.PigBotSettings, bot: commands.bot, ip: str
    ) -> None:
        self.bot = bot
        self.ip = ip + f":{config.pigbot_minecraft_server_port}"
        # initialize external ip
        self.external_ip = "Unset at startup."
        self.port = config.pigbot_minecraft_server_port
        self.server = JavaServer.lookup(self.ip)
        self.current_online = set()
        self.last_online = set()
        self.config = config
        if self.config.pigbot_minecraft_online_checks_enabled:
            self.online_checker.start()
        if self.config.pigbot_minecraft_local_server_ip_detection_enabled:
            self.ip_change_checker.start()

        self.failed_query_count = 0
        self.failed_ip_count = 0
        self.allowed_failed_queries = config.pigbot_failed_query_limit
        self.server_admin_uname = config.pigbot_minecraft_admin_uname
        self.last_known_ip_lock = asyncio.Lock()
        self.minecraft_server_lock = asyncio.Lock()

    @slash_command(description="prints the status of the minecraft server")
    async def minecraft_print_status(self, ctx):
        try:
            status = await self.server.async_status()
            if status.players.sample:
                players_string = ", ".join(p.name for p in status.players.sample)
            else:
                players_string = "None"
            title = "Minecraft server state: "
            templ = "\t - {0} : {1}"
            response = "\n".join(
                [
                    templ.format("description", "```" + status.description + "```"),
                    templ.format("ip", self.ip),
                    templ.format("version", status.version.name),
                    templ.format("latency", status.latency),
                    templ.format(
                        "player cap.", f"{status.players.online}/{status.players.max}"
                    ),
                    templ.format("players online", players_string),
                ]
            )

            await ctx.respond(
                embed=Embed(
                    title=title,
                    description=response,
                )
            )
            msg = title + response
            logger.info(msg)

        except Exception as e:
            msg = f"Received exception trying print_status for server @ ip {self.ip}! "
            description = f"Exception: '{e}'"
            logger.exception(msg + description)
            await ctx.respond(embed=Embed(title=msg, description=description))

    @slash_command(description="prints whos online playing minecraft.")
    async def minecraft_online(self, ctx):
        query = await self.query_server(ctx)
        if query is not None:
            if len(query.players.names) == 0:
                title = "No one is online currently."
                description = ""
            else:
                title = (f"The server has the following players online!",)
                description = "\n\t-".join(query.players.names)
            await ctx.respond(embed=Embed(title=title, description=description))

    @tasks.loop(seconds=10)
    async def ip_change_checker(self):
        """If pigbot is set to run in the same network as the home server, this
        checker can detect ip changes and notify the admin
        """
        async with self.last_known_ip_lock:
            current_ip = await has_ip_changed(
                self.bot, self.external_ip, self.config.pigbot_minecraft_channels
            )
            if current_ip is not None:
                await message_to_channels(
                    self.bot,
                    self.config.pigbot_minecraft_channels,
                    f"IP change detected!",
                    description=f"<@{self.server_admin_uname}> previous ip '{self.external_ip}' --> current ip '{current_ip}') :)",
                )
                await update_channel_topics(
                    self.bot,
                    self.config.pigbot_minecraft_channels,
                    f"Server IP: {current_ip}:{self.port} Server Map: http://{current_ip}:8167/",
                )
                async with self.minecraft_server_lock:
                    self.external_ip = current_ip
                    # only update server ref if not running
                    # pigbot on same server as minecraft server
                    if not self.config.pigbot_minecraft_running_on_server:
                        self.server = await JavaServer.async_lookup(
                            f"{current_ip}:{self.port}"
                        )

            else:
                logger.debug(f"No ip change detected for server with ip: {self.ip}")

    @ip_change_checker.before_loop
    async def before_ip_checker(self):
        logger.info("before_ip_checker: Waiting for bot to start.")
        await self.bot.wait_until_ready()

    @ip_change_checker.after_loop
    async def after_ip_change_checker(self):
        self.ip_change_checker.close()
        return

    @tasks.loop(seconds=2)
    async def online_checker(self):
        """Check which players are online/offline"""
        query = await self.query_server(
            channel_ids=self.config.pigbot_minecraft_channels
        )
        if query is not None:
            self.current_online = set(query.players.names)
            if self.current_online != self.last_online:
                logged_on = self.current_online.difference(self.last_online)
                logged_off = self.last_online.difference(self.current_online)
                msg = "Detected Minecraft Server Update!\n"
                desc = "\n"
                if len(logged_on) > 0:
                    desc += f"\t- Users logged on: {logged_on}\n"
                if len(logged_off) > 0:
                    desc += f"\t- Users logged off: {logged_off}\n"
                logger.info(msg)
                await message_to_channels(
                    self.bot,
                    self.config.pigbot_minecraft_channels,
                    msg=msg,
                    description=desc)

        self.last_online = self.current_online

    @online_checker.before_loop
    async def before_online_checker(self):
        logger.info("before_online_checker: Waiting for bot to start.")
        await self.bot.wait_until_ready()

    @online_checker.after_loop
    async def after_online_checker(self):
        self.online_checker.close()
        return

    @tasks.loop(seconds=10)
    async def server_online_checker(self):
        """This simply queries the server every ten seconds to confirm it is up."""
        query = await self.query_server(
            channel_ids=self.config.pigbot_minecraft_channels
        )

    @server_online_checker.before_loop
    async def before_server_online_checker(self):
        logger.info("before_server_online_checker: Waiting for bot to start.")
        await self.bot.wait_until_ready()

    @server_online_checker.after_loop
    async def after_server_online_checker(self):
        self.server_online_checker.close()
        return

    async def query_server(self, ctx=None, channel_ids=Optional[List]):
        """Query the minecraft server object

        Args:
            ctx : the discord context for sending messages. Defaults to None.
            channel [None, List]: discord channel(s) for sending messages. Defaults to None.

        Returns:
            the query response, or None is the query has failed.
        """
        try:
            query = await self.server.async_query()
            if self.failed_query_count != 0:
                # check if server connection is restored
                if self.failed_query_count + 1 >= self.allowed_failed_queries:
                    await message_to_channels(
                        self.bot,
                        channel_ids,
                        "My connection to the server has been restored!",
                    )
                # reset on success.
                self.failed_query_count = 0

            return query

        except Exception as e:
            title = f"Oink oink! I cant query the server @ ip: {self.ip}!"
            description = f"Exception: '{e}' :(. Try {self.failed_query_count+1}/{self.allowed_failed_queries}."
            if (
                self.failed_query_count + 1 < self.allowed_failed_queries
                and self.config.pigbot_log_failed_queries
            ):
                await message_to_channels(
                    self.bot, channel_ids, title, description=description
                )
            elif self.failed_query_count + 1 == self.allowed_failed_queries:
                description += f"  \nReached allowed retries <@{self.server_admin_uname}>. Disabling alerts until server is online again. For server status try $print_status."
                await message_to_channels(
                    self.bot, channel_ids, title, description=description
                )

            # if context is passed ignore retries as user is trying manual check
            if ctx is not None:
                title = f"Oink oink! I cant query the server @ ip: {self.ip}! "
                description = f"Exception: '{e}' :(."
                await ctx.send(embed=Embed(title=title, description=description))

            logger.exception(title + description)
            self.failed_query_count += 1


if __name__ == "__main__":
    pass
