import logging
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

with open('config.json') as env_config_file:
    config = json.load(env_config_file)