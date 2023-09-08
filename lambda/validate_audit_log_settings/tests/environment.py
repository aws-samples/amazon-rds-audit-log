import os
import sys
import json
import logging
import boto3

logger = logging

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # tests/
APP_DIR = os.path.normpath(os.path.join(THIS_DIR, '../app'))  # app/
BDD_UTILS = os.path.normpath(os.path.join(THIS_DIR, '../../../../'))  # bdd_utils/
STEPS_DIR = os.path.normpath(os.path.join(THIS_DIR, './steps'))  # steps/
sys.path.append(THIS_DIR)
sys.path.append(APP_DIR)
sys.path.append(BDD_UTILS)
sys.path.append(STEPS_DIR)


with open('config.json') as env_config_file:
    config = json.load(env_config_file)


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


def before_all(context):
    set_env_context_vars(context)
    from validate_audit_log_settings import boto3_client

    stack_name = f"rds-auditlog-enablement-{config['main']['environment']}"
    context.api_host = get_serverless_api_host(stack_name,
                                               env=context.env, region='us-east-1', endpoint_type='api_gateway',
                                               endpoint_stack_key='RDSAuditLogEnablerURL')

    context.rds_client = boto3_client(context, 'rds')
    context.sfn_client = boto3_client(context, 'stepfunctions')
    context.db_region = "us-east-1"


def after_all(context):
    from validate_audit_log_settings import final_db_cleanup
    final_db_cleanup(context)


def set_env_context_vars(context):
    context.db_list = {}
    context.bdd_local = True if (config['behave']['bdd_local']).lower() == 'true' else False
    context.env = config['main']['environment']
    context.region = config['main']['region']
    context.account_number = config['main']['account_number']
    context.test_account = config['main']['account_id']

    # OS Env Variables
    os.environ["env"] = config['main']['environment']
    os.environ["enable_sm_arn"] = "arn:aws:states:" + context.region + ":" + context.account_number + \
                                  ":stateMachine:RdsAuditLoggingValidationStateMachine"
