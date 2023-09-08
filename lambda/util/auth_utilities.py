import json
import logging
import os
import sys
import uuid
import boto3

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # util/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../util'))  # util/
sys.path.append(UTIL_DIR)


class Logger(object):
    def __init__(self):
        log = logging.getLogger()
        for h in log.handlers:
            h.setFormatter(logging.Formatter("[%(levelname)s]:%(message)s"))
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self._id = uuid.uuid4().hex

    def set_new_uuid(self):
        self._id = uuid.uuid4().hex

    def get_uuid(self):
        return self._id

    def set_uuid(self, id):
        self._id = id

    def error(self, msg):
        self.logger.error("{}: {}".format(self._id, msg))

    def info(self, msg):
        self.logger.info("{}: {}".format(self._id, msg))


def get_secret(secret_name: str):
    """
    Get Secret Value from Secret Manager

    Args:
         secret_name: Secret Name.

    Returns:
         str: Secret Value
    """
    try:
        region = os.environ.get('region', 'us-east-1')
        boto_client = boto3.client('secretsmanager', region_name=region)
        secret_obj = boto_client.get_secret_value(SecretId=secret_name)
        secret_value = secret_obj.get('SecretString')
        return secret_value
    except Exception as ex:
        raise Exception(f"get_secret: Failed to load secret. Details - {str(ex)}")


def auth(event):
    #  If authorization required add it here
    return True



