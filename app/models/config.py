from datetime import datetime
from typing import List, Optional
from pydantic_settings import BaseSettings
import os, sys


class PigBotSettings(BaseSettings):
    """Configuration using .env file

    Args:
        BaseSettings (pydantic.BaseSettings): BaseSettings object from pydantic
    """

    env: str
    pigbot_token: str
    pigbot_minecraft_server_ip: str
    # enable this flag if you are running pigbot on the
    # same server as minecraft.
    pigbot_minecraft_running_on_server: bool = False
    pigbot_minecraft_server_port: int
    pigbot_minecraft_channels: List[str]
    pigbot_failed_query_limit: int = 25565
    pigbot_minecraft_admin_uname: str
    pigbot_log_failed_queries: bool = False
    pigbot_minecraft_enable: bool = True
    pigbot_minecraft_online_checks_enabled: bool = True
    pigbot_dalle_enable: bool = True
    pigbot_dalle_ip: str = "localhost"
    pigbot_dalle_port: int = 8000
    pigbot_minecraft_local_server_ip_detection_enabled: bool = False
    pigbot_dalle_max_number_of_images: int = 4

    class Config:
        config_path = os.path.join(
            os.path.dirname(sys.path[0]), f"{os.getenv('ENV','')}.env"
        )
        env_file = config_path
        env_file_encoding = "utf-8"
