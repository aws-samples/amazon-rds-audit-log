"""
Env file for BDD
"""
# pylint: disable=import-error, missing-function-docstring, unused-import, no-else-break
import os
import boto3
import json
import sys
import logging

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # tests/
APP_DIR = os.path.normpath(os.path.join(THIS_DIR, '../app'))  # app/
STEPS_DIR = os.path.normpath(os.path.join(THIS_DIR, './steps'))  # steps/
BDD_UTILS = os.path.normpath(os.path.join(THIS_DIR, '../../../../'))  # bdd_utils/
sys.path.append(THIS_DIR)
sys.path.append(APP_DIR)
sys.path.append(STEPS_DIR)
sys.path.append(BDD_UTILS)

with open('config.json') as env_config_file:
    config = json.load(env_config_file)

logger = logging


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

    context.config = config
    from service_enable_audit import boto3_client

    stack_name = f"rds-auditlog-enablement-{config['main']['environment']}"
    context.api_host = get_serverless_api_host(stack_name,
                                               env=context.env, region='us-east-1',
                                               endpoint_type="alb",
                                               endpoint_stack_key='RDSAuditLogEnablerURL')
    print (context.api_host )
    context.rds_client = boto3_client(context, 'rds', config['behave']['account_number'])
    context.sfn_client = boto3_client(context, 'stepfunctions')


def before_feature(context, feature):
    from service_enable_audit import setup_test_rds_instance
    from steps_enable_oracle import check_rds_instance
    if "rds-audit-log-oracle" in context.feature.tags:
        context.db_identifier = "test-oracle19"
        context.db_identifier_12 = "test-oracle12"
        context.engine = "oracle-ee"
        context.version = "19.0.0.0.ru-2021-04.rur-2021-04.r1"
        context.port = 1521
        context.user = 'admin'
        context.engine_mode = None
        context.instance_or_cluster = 'instance'
        #  setup oracle 12
        # setup_rds_instance(context, context.db_identifier_12)
        # setup oracle 19
        setup_test_rds_instance(context)
        check_rds_instance(context, context.db_identifier)
    print("success")
    context.db_region = "us-east-1"


def after_feature(context, feature):
    from service_enable_audit import final_db_cleanup
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
