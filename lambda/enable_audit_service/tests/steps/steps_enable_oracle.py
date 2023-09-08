"""
Steps file for enable_audit BDD
"""
# pylint: disable=too-many-statements, too-many-locals, no-member, wrong-import-order, import-error, wrong-import-position, global-variable-undefined, unused-argument, missing-module-docstring, wildcard-import, bad-option-value, line-too-long, missing-final-newline, trailing-whitespace, disable=broad-except, simplifiable-if-expression, f-string-without-interpolation,function-redefined, undefined-variable, missing-function-docstring, logging-fstring-interpolation, logging-string-interpolation, unused-wildcard-import, unused-variable, logging-not-lazy, unused-import

import os
import sys
import json
import time
import logging
import requests
import boto3

from unittest import mock
from hamcrest import assert_that, equal_to
from behave import *
from retry import retry

LOG_LEVEL = 'log_level'
logger = logging.getLogger()
logger.setLevel(os.environ.get(LOG_LEVEL, logging.INFO))

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # steps/
APP_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../app'))  # app/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../../util'))  # util/
sys.path.append(THIS_DIR)
sys.path.append(APP_DIR)
sys.path.append(UTIL_DIR)


def boto3_client(context, account, service):
    client = boto3.client(
        region_name=context.region,
        service_name=service,
    )
    return client


@given(u'POST API /v1/rdsauditlog exists')
def step_impl(context):
    pass


@when(u'we invoke POST API /v1/rdsauditlog')
def step_impl(context):
    from enable_audit_handler import handler
    # Bad Auth Token
    if 'error_type_token' in context:
        if context.error_type_token is None:
            event_with_auth = {'body': json.dumps(
                dict(account_id=context.test_account,
                     region=context.region,
                     instance_or_cluster=context.instance_or_cluster,
                     db_identifier=context.db_identifier)
            )}
        else:
            event_with_auth = {'headers': {'authorization': context.error_type_token,
                                           'Content-Type': 'application/json',
                                           'Accept': '*/*'},
                               'body': json.dumps(
                                   dict(account_id=context.test_account,
                                        region=context.region,
                                        instance_or_cluster=context.instance_or_cluster,
                                        db_identifier=context.db_identifier)
                               )}
        if context.bdd_local:
            handler_output = handler(event_with_auth, '')
        else:
            url = f'http://{context.api_host}/v1/rdsauditlog'
            headers = (event_with_auth["headers"] if 'headers' in event_with_auth else {})
            body = event_with_auth["body"]
            response = requests.post(url, data=body, headers=headers)

    # Good Auth Token
    else:
        with mock.patch('enable_audit_handler.db_created_less_than_1hr') as mock_db:
            # If cluster mode=provisioned then change from cluster to instance
            # If cluster mode=serverless then leave as cluster, change db_id to cluster_id
            mock_db.return_value = True

            event_with_auth = {'headers': {'authorization': context.generated_token,
                                           'Content-Type': 'application/json'},
                               'body': json.dumps(
                                   dict(account_id=context.test_account,
                                        region=context.region,
                                        instance_or_cluster=context.instance_or_cluster,
                                        db_identifier=context.db_identifier)
                               )}

            # DO NOT MOVE BELOW, as it falls under mock_db patch to get sfn validation to complete under 1h db criteria
            # Mock only applies to BDD local else BDD is API invoked
            if context.bdd_local:
                handler_output = handler(event_with_auth, '')
            else:
                url = f'http://{context.api_host}/v1/rdsauditlog'
                headers = (event_with_auth["headers"] if 'headers' in event_with_auth else {})
                body = event_with_auth["body"]
                response = requests.post(url, data=body, headers=headers)

    if context.bdd_local:
        context.lambda_status_code = str(handler_output['statusCode'])
        response_body = json.loads(handler_output['body'])
    else:
        context.lambda_status_code = str(response.status_code)
        response_body = json.loads(response.text)

    # Error message
    if 'error' in response_body:
        context.lambda_status_message = response_body['error']
    # Success message
    elif 'message' in response_body and 'sfn_execution_arn' in response_body:
        context.lambda_status_message = response_body['message']
        context.sfn_execution_arn = response_body['sfn_execution_arn']
    else:
        assert False
    pass


@then(u'{log_destination} contains details about who performed action and at what time')
def step_impl(context, log_destination):
    pass


# RDS Instances
def setup_rds_instance(context, db_identifier='test-123-oracle12', engine_version='12.1.0.2.v25'):
    """
    Function to setup RDS instance
    @param context:
    @param db_identifier:
    @param engine_version:
    @return:
    """
    try:
        # create instance
        db_inst_class = 'db.r5.large' if context.version.startswith('9.6') else 'db.t3.medium'
        context.rds_client.create_db_instance(
            VpcSecurityGroupIds=context.config['main']['db_vpc_security_group_name'],
            DBInstanceIdentifier=db_identifier,
            Engine=context.engine,
            EngineVersion=engine_version,
            Port=int(context.port),
            MasterUsername=context.user,
            # MasterUserPassword=context.config['behave']['db_master_password'],
            DBInstanceClass=db_inst_class,
            PubliclyAccessible=False,
            DBSubnetGroupName=context.config['main']['db_subnet_group_name'],
            AllocatedStorage=10,
            ManageMasterUserPassword=True
        )
        return True
    except Exception as e:
        if 'DBInstanceAlreadyExists' in str(e):
            return True
        logger.error(f'Error {str(e)}')
        return False


def check_instance_running(context, db_identifier):
    try:
        db_instances = context.rds_client.describe_db_instances(DBInstanceIdentifier=db_identifier)
        db_instance = db_instances["DBInstances"][0]
        db_id = db_instance['DBInstanceIdentifier']
        status = db_instance['DBInstanceStatus']

        if status == 'available':
            logger.info(f'Database {db_id} is \"Available\"')
            return True
        logger.info(f'Database {db_id} is not in \"Available\" state. Current state={status}')
        return False

    except Exception as err:
        error_message = err.response['Error']['Message']
        logger.error(f'Error: {error_message}')
        return False


def check_rds_instance(context, db_identifier):
    delay = 1
    flag = True
    while True:
        instance_ready = check_instance_running(context, db_identifier)
        if instance_ready:
            break
        time.sleep(10)
        delay += 1
        if delay == 1000:
            flag = False
            break
    if flag:
        return True
    return False


