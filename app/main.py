import datetime
import logging

from api.dalle import Dalle
from api.messaging import Common
from api.minecraft import Minecraft
from api.songbird import Songbird
from discord import Intents
from discord.ext import commands
from models import config
from util import logutil

logger = logging.getLogger(__name__)

VERSION = "0.1.4"


def main():
    logutil.set_logger_config_globally(
        datetime.datetime.now().strftime("YYYY_mm_dd_HH:MM:SS")
    )
    logger.info(f"Starting up Pigbot {VERSION}!")
    pigbot_config = config.PigBotSettings()
    intents = Intents.default()
    intents.message_content = True
    bot = commands.Bot(intents=intents)
    bot.add_cog(Common(bot))
    if pigbot_config.pigbot_minecraft_enable:
        bot.add_cog(
            Minecraft(pigbot_config, bot, pigbot_config.pigbot_minecraft_server_ip)
        )
    logger.info(pigbot_config.pigbot_token)
    if pigbot_config.pigbot_dalle_enable:
        bot.add_cog(
            Dalle(
                pigbot_config,
                bot,
                pigbot_config.pigbot_dalle_ip,
                pigbot_config.pigbot_dalle_port,
            )
        )
    if pigbot_config.pigbot_songbird_enable:
        bot.add_cog(
            Songbird(
                pigbot_config,
                bot,
            )
        )
    bot.run(pigbot_config.pigbot_token)


if __name__ == "__main__":
    main()
