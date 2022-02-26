import datetime
import logging
from discord.ext import commands
from api.messaging import Common
from api.minecraft import Minecraft
from models import config
from util import logutil

logger = logging.getLogger(__name__)
def main():
    logutil.set_logger_config_globally(datetime.datetime.now().strftime('YYYY_mm_dd_HH:MM:SS'))
    logger.info("Starting up Pigbot!")
    pigbot_config = config.loader()
    bot = commands.Bot(command_prefix="$")
    bot.add_cog(Common(bot))
    bot.add_cog(Minecraft(pigbot_config, bot, pigbot_config.pigbot_minecraft_server_ip))
    bot.run(pigbot_config.pigbot_token)

if __name__=="__main__":
    main()