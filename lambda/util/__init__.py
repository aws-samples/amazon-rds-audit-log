# pylint:disable=wrong-import-position,wrong-import-order, import-error, W0703
import logging
import json
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)
print("working windows",os.getcwd())
# with open('../../../config/config.{}.json'.format(os.environ['ENV'])) as env_config_file:
#     config = json.load(env_config_file)

# Load from env variables
# os.environ['azure_auth_secret_name'] = config['behave']['azure_auth_secret_name']
# os.environ['ldap_group_name'] = config['behave']['ldap_group_name']
# os.environ['msft_tenant_id'] = config['behave']['msft_tenant_id']
# os.environ['msft_app_id'] = config['behave']['msft_app_id']
# os.environ['msft_client_roles'] = config['behave']['msft_client_roles']
# os.environ['azure_auth_client_id'] = config['behave']['azure_auth_client_id']
