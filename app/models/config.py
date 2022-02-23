from datetime import datetime
from typing import List, Optional
from pydantic import BaseSettings
import os, sys

class PigBotSettings(BaseSettings):
    token: str


def loader():
    """Config loader (expects .env file within root directory of project)
    """
    config_path = os.path.join(os.path.dirname(sys.path[0]), '.env')
    return PigBotSettings(_env_file=config_path, _env_file_encoding='utf-8')