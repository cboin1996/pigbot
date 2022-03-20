from typing import List, Optional
from mcstatus import MinecraftServer
import sys
from discord.ext import tasks, commands
import logging
from models import config

logger = logging.getLogger(__name__)

class Minecraft(commands.Cog):
    def __init__(self, config: config.PigBotSettings, bot: commands.bot, ip: str) -> None:
        self.bot = bot
        self.ip = ip
        self.server = MinecraftServer.lookup(self.ip)
        self.current_online = set()
        self.last_online = set()
        self.online_checker.start()
        self.config = config
        self.failed_query_count = 0
        self.allowed_failed_queries = config.pigbot_failed_query_limit
        self.server_admin_uname = config.pigbot_minecraft_admin_uname

    @commands.command(
        brief="prints the status of the minecraft server"
    )
    async def print_status(self, ctx):
        try:
            status = self.server.status()
            if status.players.sample:
                players_string = ', '.join(p.name for p in status.players.sample)
            else:
                players_string = ''

            response = ('{0} ({1}) v{2} {3}ms {4}/{5}{6}{7}'.format(
                status.description,
                self.ip,
                status.version.name,
                status.latency,
                status.players.online,
                status.players.max,
                bool(players_string)*' ',  # Only include space if there is data.
                players_string,
            ))
            msg = f"Minecraft server state:\n\t{response}"
            await ctx.send(msg)

        except Exception as e:
            msg = f"I cant reach the server @ ip {self.ip}. Is it down?"
            await ctx.send(msg)

    @commands.command(
        brief="prints whos online playing minecraft."
    )
    async def online(self, ctx):
        query = await self.query_server(ctx)
        if query is not None:
            await ctx.send(f"The server has the following players online: {', '.join(query.players.names)}")

    
    @tasks.loop(seconds=10)
    async def online_checker(self):
        query = await self.query_server(channel_ids=self.config.pigbot_discord_channels)
        if query is not None:
            self.current_online = set(query.players.names)
            if self.current_online != self.last_online:
                logged_on  = self.current_online.difference(self.last_online)
                logged_off = self.last_online.difference(self.current_online)
                msg = "Detected Minecraft Server Update!\n"
                if len(logged_on) > 0:
                    msg += f"\t- Users logged on: {logged_on}\n"
                if len(logged_off) > 0:
                    msg += f"\t- Users logged off: {logged_off}\n"
                logger.info(msg)
                await self.message_to_channels(self.config.pigbot_discord_channels, msg)
        
        self.last_online = self.current_online

    @online_checker.before_loop
    async def before_online_checker(self):
        logger.info("Waiting for bot to start.")
        await self.bot.wait_until_ready()

    @online_checker.after_loop  
    async def after_online_checker(self):
      self.online_checker.close()
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
            query = self.server.query()
            if self.failed_query_count != 0:
                await self.message_to_channels(channel_ids, "It appears the server has come back on!")
                # reset on success.
                self.failed_query_count = 0

            return query

        except Exception as e:
            msg = f"Oink oink! I cant query the server @ ip: {self.ip}! Exception: '{e}' :(. Try {self.failed_query_count+1}/{self.allowed_failed_queries}."
            if self.failed_query_count+1 < self.allowed_failed_queries:
                await self.message_to_channels(channel_ids, msg)
            elif self.failed_query_count+1 == self.allowed_failed_queries:
                msg += f"  Reached allowed retries <@{self.server_admin_uname}>. Disabling alerts until server is online again. For server status try $print_status."
                await self.message_to_channels(channel_ids, msg)

            # if context is passed ignore retries as user is trying manual check
            if ctx is not None:
                msg = f"Oink oink! I cant query the server @ ip: {self.ip}! Exception: '{e}' :(."
                await ctx.send(msg)
        
            logger.exception(msg)
            self.failed_query_count += 1
    
    async def message_to_channels(self, channel_ids: List[str], msg: str):
        """Outputs message to given discord channels

        Args:
            channel_ids (List[str]): the list of discord channel ids
            msg (str): the message
        """
        if channel_ids is not None:
            for channel_id in channel_ids:
                channel = self.bot.get_channel(int(channel_id))
                await channel.send(msg)

if __name__=="__main__":
    pass