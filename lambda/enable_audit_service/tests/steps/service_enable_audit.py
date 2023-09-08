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


def boto3_client(context, service, account=None):
    client = boto3.client(
        region_name=context.region,
        service_name=service,
    )
    return client


def final_db_cleanup(context):
    for db_identifier in context.db_list:
        instance_or_cluster = context.db_list[db_identifier]['instance_or_cluster']
        cluster_identifier = context.db_list[db_identifier]['cluster_identifier']
        engine_mode = context.db_list[db_identifier]['engine_mode']
        logger.info(f'DB deletion: db_id={db_identifier}, instance_or_cluster={instance_or_cluster}, '
                    f'cluster_identifier={cluster_identifier}, engine_mode={engine_mode}')

        cleanup_test_rds(context, db_identifier, instance_or_cluster, cluster_identifier, engine_mode)


def cleanup_test_rds(context, db_identifier, instance_or_cluster, cluster_identifier, engine_mode):
    if (instance_or_cluster == 'instance') or (engine_mode == 'provisioned'):
        try:
            logger.info("Deleting DB Instance")
            context.rds_client.delete_db_instance(DBInstanceIdentifier=db_identifier, SkipFinalSnapshot=True,
                                                  DeleteAutomatedBackups=True)
            logger.info("Deleted DB Instance")
            time.sleep(10)
        except Exception as err:
            logger.error(f'Instance deletion error: {str(err)}')
            return False

    if instance_or_cluster == 'instance':
        return True

    if instance_or_cluster == 'cluster':
        try:
            logger.info("Deleting DB Cluster")
            context.rds_client.delete_db_cluster(DBClusterIdentifier=cluster_identifier,
                                                 SkipFinalSnapshot=True)
            logger.info("Deleted DB Cluster")
            time.sleep(10)
        except Exception as e:
            logger.error(f'Serverless cluster deletion error: {str(e)}')
            return False

    return True


# Aurora Clusters
def check_cluster_exists(context):
    """
    Function check to verify if cluster exists
    @param context:
    @return:
    """
    try:
        db_clusters = context.rds_client.describe_db_clusters(DBClusterIdentifier=context.db_cluster_identifier)
        writer_instance_list = []
        cluster = db_clusters["DBClusters"][0]
        cluster_member_list = cluster["DBClusterMembers"]

        # If cluster is serverless then return as no instances
        if cluster['EngineMode'] == 'serverless':
            logger.info(f"Serverless cluster found: {context.db_cluster_identifier}")
            return True

        for i in cluster_member_list:
            if i["IsClusterWriter"]:
                writer_instance_list.append(i["DBInstanceIdentifier"])

        if writer_instance_list:
            logger.info(f"Writer instance found: {writer_instance_list}")
            return True
        return False
    except Exception as err:
        logger.info(f"{str(err)}")
        return False


def setup_rds_cluster(context):
    """
    Function to setup RDS cluster
    @param context:
    @return:
    """
    try:
        if 'engine_mode' not in context:
            context.engine_mode = 'serverless'
        if context.engine_mode == 'serverless':
            context.rds_client.create_db_cluster(
                VpcSecurityGroupIds=context.config['main']['db_vpc_security_group_name'],
                DBSubnetGroupName=context.config['main']['db_subnet_group_name'],
                BackupRetentionPeriod=1,
                DBClusterIdentifier=context.db_cluster_identifier,
                DatabaseName=context.config['behave']['db_name'],
                Engine=context.engine,
                EngineVersion=context.version,
                MasterUsername=context.user,
                MasterUserPassword=context.config['behave']['db_master_password'],
                Port=int(context.port),
                StorageEncrypted=True,
                EngineMode=context.engine_mode,
            )
        else:
            context.rds_client.create_db_cluster(
                VpcSecurityGroupIds=context.config['main']['db_vpc_security_group_name'],
                DBSubnetGroupName=context.config['main']['db_subnet_group_name'],
                BackupRetentionPeriod=1,
                DBClusterIdentifier=context.db_cluster_identifier,
                DatabaseName=context.config['behave']['db_name'],
                Engine=context.engine,
                EngineVersion=context.version,
                MasterUsername=context.user,
                Port=int(context.port),
                StorageEncrypted=True,
                EngineMode=context.engine_mode,
                ManageMasterUserPassword=True
            )
        return True
    except Exception as err:
        if 'DBClusterAlreadyExistsFault' in str(err):
            return True
        logger.error(f'Error {str(err)}')
        return False


def setup_rds_cluster_instance(context):
    """
    Function to setup RDS cluster instance
    @param context:
    @return:
    """
    try:
        # create cluster
        db_inst_class = 'db.m6i.large' if context.version.startswith('14.4') else 'db.t3.medium'
        context.rds_client.create_db_instance(
            DBInstanceClass=db_inst_class,
            DBInstanceIdentifier=context.db_identifier,
            Engine=context.engine,
            DBClusterIdentifier=context.db_cluster_identifier
        )
        return True
    except Exception as e:
        if 'DBInstanceAlreadyExists' in str(e):
            return True
        logger.error(f'Error {str(e)}')
        return False


def setup_test_rds_cluster(context):
    while True:
        already_exist = check_cluster_exists(context)
        if already_exist:
            if context.engine_mode == 'serverless':
                return True
            break
        else:
            logger.info('Creating database cluster: ' + context.db_cluster_identifier)
            setup_rds_cluster(context)
            time.sleep(10)
            if context.engine_mode == 'serverless':
                return True
            logger.info('Creating database cluster instance: ' + context.db_identifier)
            setup_rds_cluster_instance(context)
            time.sleep(10)

    while True:
        instance_ready = check_instance_running(context)
        if instance_ready:
            break
        time.sleep(10)
    return True


# RDS Instances
def setup_rds_instance(context):
    """
    Function to setup RDS instance
    @param context:
    @return:
    """
    try:
        # create instance
        if context.engine == 'sqlserver-ee':
            context.rds_client.create_db_instance(
                VpcSecurityGroupIds=context.config['main']['db_vpc_security_group_name'],
                DBInstanceIdentifier=context.db_identifier,
                Engine=context.engine,
                EngineVersion=context.version,
                Port=int(context.port),
                MasterUsername=context.user,
                DBInstanceClass='db.t3.xlarge',
                PubliclyAccessible=False,
                DBSubnetGroupName=context.config['main']['db_subnet_group_name'],
                StorageType='gp2',
                AllocatedStorage=20,
                LicenseModel='license-included',
                ManageMasterUserPassword=True
            )
        else:
            db_inst_class = 'db.m6i.large' if context.version.startswith('14.4') else 'db.t3.medium'
            context.rds_client.create_db_instance(
                VpcSecurityGroupIds=context.config['main']['db_vpc_security_group_name'],
                DBInstanceIdentifier=context.db_identifier,
                Engine=context.engine,
                EngineVersion=context.version,
                Port=int(context.port),
                MasterUsername=context.user,
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


def check_instance_exists(context):
    try:
        db_instances = context.rds_client.describe_db_instances(DBInstanceIdentifier=context.db_identifier)

        if db_instances["DBInstances"][0]:
            instance = db_instances["DBInstances"][0]['DBInstanceIdentifier']
            logger.info(f"Database {instance} now exists")
            return True
        logger.info("Database does not exist")
        return False
    except Exception as err:
        error_message = err.response['Error']['Message']
        logger.error(f'Error: {error_message}')
        return False


def check_instance_running(context):
    try:
        db_instances = context.rds_client.describe_db_instances(DBInstanceIdentifier=context.db_identifier)
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


def setup_test_rds_instance(context):
    while True:
        already_exist = check_instance_exists(context)
        if already_exist:
            break
        logger.info('Creating database instance: ' + context.db_identifier)
        setup_rds_instance(context)
        time.sleep(10)

    while True:
        instance_ready = check_instance_running(context)
        if instance_ready:
            break
        time.sleep(60)

    return True


def setup_data(context):
    # initialize for use in failure tests
    if 'instance_or_cluster' not in context:
        context.instance_or_cluster = 'instance'
    if 'db_identifier' not in context:
        context.db_identifier = 'TestDB'


# Test for 'Failure to invoke RDS Audit Log API'
@given(u'an account exists')
def step_impl(context):
    context.test_account = context.config['main']['account_id']


@when(u'we invoke RDS Audit Log API lambda function')
def step_impl(context):
    from enable_audit_handler import handler
    # Initialize
    setup_data(context)

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
            url = f'http://{context.api_host}/dev/v1/rds_audit_log'
            headers = (event_with_auth["headers"] if 'headers' in event_with_auth else {})
            body = event_with_auth["body"]
            response = requests.post(url, data=body, headers=headers)

    # Good Auth Token
    else:
        with mock.patch('enable_audit_handler.db_created_less_than_1hr') as mock_db:
            # If cluster mode=provisioned then change from cluster to instance
            # If cluster mode=serverless then leave as cluster, change db_id to cluster_id
            mock_db.return_value = True
            token_bearer = "Bearer "
            if context.instance_or_cluster == 'cluster':
                if context.engine_mode:
                    if context.engine_mode == 'provisioned':
                        event_with_auth = {'headers': {'authorization': token_bearer,
                                                       'Content-Type': 'application/json;charset=utf-8',
                                                       'Accept': '*/*'},
                                           'body': json.dumps(
                                               dict(account_id=context.test_account,
                                                    region=context.region,
                                                    instance_or_cluster='instance',
                                                    db_identifier=context.db_identifier)
                                           )}
                    else:
                        event_with_auth = {'headers': {'authorization': token_bearer,
                                                       'Content-Type': 'application/json;charset=utf-8',
                                                       'Accept': '*/*'},
                                           'body': json.dumps(
                                               dict(account_id=context.test_account,
                                                    region=context.region,
                                                    instance_or_cluster=context.instance_or_cluster,
                                                    db_identifier=context.db_cluster_identifier)
                                           )}
            else:
                event_with_auth = {'headers': {'authorization': token_bearer,
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


@then(u'API response contains a status code of {expected_status_code}')
def step_impl(context, expected_status_code):
    logger.info(f'API response contains a status code of {context.lambda_status_code}')
    assert_that(expected_status_code, equal_to(context.lambda_status_code))


@given(u'an authorized user makes the API call')
def step_impl(context):
    pass


@step(u'{instance_or_cluster} exists with details {identifier}, {engine}, {version}, {port}, {user}, {mode}')
def step_impl(context, instance_or_cluster, identifier, engine, version, port, user, mode):
    if "rds-audit-log-oracle" in context.feature.tags:
        if "oracle12" in identifier:
            context.db_identifier = context.db_identifier_12
    else:
        if instance_or_cluster in ['instance', 'cluster']:
            context.instance_or_cluster = instance_or_cluster
            context.db_identifier = identifier if instance_or_cluster == 'instance' else identifier + '-instance-1'
            context.db_cluster_identifier = identifier if instance_or_cluster == 'cluster' else None
            context.engine = engine
            context.version = version
            context.port = port
            context.user = user
            context.engine_mode = None if mode == 'None' else mode
            #
            context.db_list[context.db_identifier] = {'instance_or_cluster': context.instance_or_cluster,
                                                      'cluster_identifier': context.db_cluster_identifier,
                                                      'engine_mode': context.engine_mode}

            # setup cluster with instance or just instance
            if instance_or_cluster == 'instance':
                setup_test_rds_instance(context)
            else:
                setup_test_rds_cluster(context)
        else:
            assert False


@step("response contains the Step Function execution ARN which does the validation")
def step_impl(context):
    if 'sfn_execution_arn' in context:
        logger.info(f'sfn_execution_arn={context.sfn_execution_arn}')
    else:
        logger.error('sfn_execution_arn not found in context')
    assert True if (os.environ.get("enable_sm_arn") and 'sfn_execution_arn' in context) is not None else False


@step("response contains the enablement success message")
def step_impl(context):
    expected_message = "Audit logging has been successfully enabled"
    logger.info("expected_message = Audit logging has been successfully enabled")
    assert_that(expected_message, equal_to(context.lambda_status_message))


@step("the Step Function instance is running")
def step_impl(context):
    if 'sfn_execution_arn' in context:
        sfn_execution_arn = context.sfn_execution_arn
        context.exec_response = context.sfn_client.describe_execution(executionArn=sfn_execution_arn)
        logger.info({'initial exec_response': context.exec_response})
        while context.exec_response.get('status') == 'RUNNING':
            time.sleep(30)
            logger.info({'running exec_response': context.exec_response})
            context.exec_response = context.sfn_client.describe_execution(executionArn=sfn_execution_arn)
        logger.info({'final exec_response': context.exec_response})
    else:
        assert False


@step("the Step Function executes successfully to validate the audit setup")
def step_impl(context):
    sfn_execution_status = json.loads(context.exec_response.get('output', 'failed'))
    logger.info({'final sfn_execution_status': sfn_execution_status})
    assert True if sfn_execution_status['status'] == 'success' else False


@then("API returns message on failed audit log enablement")
def step_impl(context):
    expected_message = "Failure in Audit Log enablement. Details: Success not returned during audit enablement"
    assert_that(expected_message, equal_to(context.lambda_status_message))


@step(u'we invoke validation step function')
def step_impl(context):
    assert True if (os.environ.get("enable_sm_arn") and 'sfn_execution_arn' in context) is not None else False


# Failed validation - Step Fn run

@given("RDS instance exists")
def step_impl(context):
    context.instance_or_cluster = 'instance'
    context.db_identifier = 'mysql-validate-check'
    context.db_cluster_identifier = 'mysql-validate-check'
    context.engine = 'mysql'
    context.version = '5.7.39'
    context.port = '3306'
    context.user = 'admin'
    context.engine_mode = None
    #
    context.db_list[context.db_identifier] = {'instance_or_cluster': context.instance_or_cluster,
                                              'cluster_identifier': context.db_cluster_identifier,
                                              'engine_mode': context.engine_mode}

    # setup cluster with instance or just instance
    setup_test_rds_instance(context)
