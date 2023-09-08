"""
This file is used for cw logs export to s3
"""

# pylint: disable=broad-except, wrong-import-position, no-name-in-module,unused-argument, logging-fstring-interpolation
import json
import requests
import logging
import os
import sys
import boto3

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # app/
API_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../'))  # lambda/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../util'))  # util/
sys.path.append(THIS_DIR)
sys.path.append(API_DIR)
sys.path.append(UTIL_DIR)
from client_utilities import ClientUtilities

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_serverless_api_host(
        stack_name, env='dev', region='us-east-1',
        endpoint_type='api_gateway',
        endpoint_stack_key='ServiceEndpoint'
):
    cf_client = boto3.client(
        service_name='cloudformation', region_name=region,
    )

    stack_info = {}
    try:
        stack_info = cf_client.describe_stacks(
            StackName=stack_name
        )
        api_host = ''
        for item in stack_info['Stacks'][0]['Outputs']:
            if item['OutputKey'] == endpoint_stack_key:
                api_host = item['OutputValue']
                break
        if not api_host:
            msg = f"Key '{endpoint_stack_key}' not found in stack '{stack_name}'."
            logging.error(msg)
            raise Exception(msg)
        if endpoint_type == 'api_gateway':
            return (
                api_host.replace('https://', '').replace(f"/{env}", '')
            )
        elif endpoint_type == 'alb':
            return api_host
        else:
            raise NotImplementedError(f"Implementation missing for endpoint type '{endpoint_type}'")
    except Exception as err:
        logging.error(
            f"Failed to Set API host to context. Error - '{str(err)}', stack_info = {str(stack_info)}"
        )
        raise err


def handler(event, context):
    logger.info(f'event -- {event}')
    env = os.environ.get('env')
    stack_name = f"rds-auditlog-enablement-{env}"
    logger.info(f'stack_name -- {stack_name}')
    api_host = get_serverless_api_host(stack_name,
                                       env=env, region='us-east-1',
                                       endpoint_type="alb",
                                       endpoint_stack_key='RDSAuditLogEnablerURL')
    account = event.get('account')
    region = event.get('region')
    db_identifier = event.get('detail').get('requestParameters').get('dBInstanceIdentifier')
    instance_or_cluster = "cluster" if "aurora" in event.get('detail').get('requestParameters').get('engine') \
        else "instance"
    logger.info(f"api_host-- {api_host}, db_identifier-- {db_identifier}")
    target_client = ClientUtilities()
    rds_client = target_client.boto3_client(account, 'rds', region)
    if instance_or_cluster == "instance":
        waiter = rds_client.get_waiter("db_instance_available")
        waiter.wait(
            DBInstanceIdentifier=db_identifier)
    else:
        waiter = rds_client.get_waiter("db_cluster_available")
        waiter.wait(
            DBClusterIdentifier=db_identifier)
    event_with_auth = {'headers': {'authorization': "Bearer ",
                                   'Content-Type': 'application/json'},
                       'body': json.dumps(
                           dict(account_id=account,
                                region=region,
                                instance_or_cluster=instance_or_cluster,
                                db_identifier=db_identifier)
                       )}
    url = f'http://{api_host}/v1/rds_audit_log'
    headers = (event_with_auth["headers"] if 'headers' in event_with_auth else {})
    body = event_with_auth["body"]
    logger.info(f"body-- {body}, url-- {url}")
    response = requests.post(url, data=body, headers=headers)
    logger.info(f"response is - {response}")

