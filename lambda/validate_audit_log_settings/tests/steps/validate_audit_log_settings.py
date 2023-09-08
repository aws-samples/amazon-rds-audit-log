# pylint: disable=missing-module-docstring, wildcard-import, bad-option-value, line-too-long, missing-final-newline, trailing-whitespace, disable=broad-except, simplifiable-if-expression, f-string-without-interpolation,function-redefined, undefined-variable, missing-function-docstring, logging-fstring-interpolation, logging-string-interpolation, unused-wildcard-import, unused-variable, logging-not-lazy, unused-import
import json
import logging
import os
import sys
import time
import boto3
from datetime import datetime, timedelta
from unittest import mock

import requests
from behave import *
from hamcrest import assert_that, equal_to
from retry import retry

LOG_LEVEL = 'log_level'
logger = logging.getLogger()
logger.setLevel(os.environ.get(LOG_LEVEL, logging.INFO))

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # steps/
APP_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../../enable_audit_service/app'))  # app/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../../util'))  # util/
sys.path.append(THIS_DIR)
sys.path.append(APP_DIR)
sys.path.append(UTIL_DIR)

# from enable_audit_handler import handler

with open('config.json') as env_config_file:
    config = json.load(env_config_file)


##############
#   Helpers
##############


def boto3_client(context, service):
    client = boto3.client(
        region_name=context.region,
        service_name=service
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
    except Exception as e:
        return False


def setup_rds_cluster(context):
    """
    Function to setup RDS cluster
    @param context:
    @return:
    """
    Maintenance_start = (datetime.now() + timedelta(hours=3)).strftime("%a:%H:%M")
    Maintenance_end = (datetime.now() + timedelta(hours=3, minutes=30)).strftime("%a:%H:%M")
    MaintenanceWindow = Maintenance_start + "-" + Maintenance_end

    try:
        if 'engine_mode' not in context:
            context.engine_mode = 'serverless'
        if context.engine_mode == 'serverless':
            context.rds_client.create_db_cluster(
                VpcSecurityGroupIds=config['main']['db_vpc_security_group_name'],
                DBSubnetGroupName=config['main']['db_subnet_group_name'],
                BackupRetentionPeriod=1,
                DBClusterIdentifier=context.db_cluster_identifier,
                DatabaseName=config['behave']['db_name'],
                Engine=context.engine,
                EngineVersion=context.version,
                MasterUsername=context.user,
                MasterUserPassword=config['behave']['db_master_password'],
                Port=int(context.port),
                StorageEncrypted=True,
                EngineMode=context.engine_mode,
            )
        else:
            context.rds_client.create_db_cluster(
                VpcSecurityGroupIds=config['main']['db_vpc_security_group_name'],
                AvailabilityZones=[config['main']['db_cluster_availability_zone']],
                DBSubnetGroupName=config['main']['db_subnet_group_name'],
                BackupRetentionPeriod=1,
                DBClusterIdentifier=context.db_cluster_identifier,
                DatabaseName=config['behave']['db_name'],
                Engine=context.engine,
                EngineVersion=context.version,
                MasterUsername=context.user,
                Port=int(context.port),
                StorageEncrypted=True,
                EngineMode=context.engine_mode,
                PreferredMaintenanceWindow=MaintenanceWindow,
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
        db_inst_class = 'db.r5.large' if context.version.startswith('9.6') else 'db.t3.medium'
        context.rds_client.create_db_instance(
            DBInstanceClass=db_inst_class,
            DBInstanceIdentifier=context.db_identifier,
            Engine=context.engine,
            DBClusterIdentifier=context.db_cluster_identifier,
            ManageMasterUserPassword=True

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
    Maintenance_start = (datetime.now() + timedelta(hours=3)).strftime("%a:%H:%M")
    Maintenance_end = (datetime.now() + timedelta(hours=3, minutes=30)).strftime("%a:%H:%M")
    MaintenanceWindow = Maintenance_start + "-" + Maintenance_end

    try:
        # create instance
        if context.engine == 'sqlserver-ee':
            context.rds_client.create_db_instance(
                VpcSecurityGroupIds=config['main']['db_vpc_security_group_name'],
                DBInstanceIdentifier=context.db_identifier,
                Engine=context.engine,
                EngineVersion=context.version,
                Port=int(context.port),
                MasterUsername=context.user,
                # MasterUserPassword=config['behave']['db_master_password'],
                DBInstanceClass='db.t3.xlarge',
                PubliclyAccessible=False,
                DBSubnetGroupName=config['main']['db_subnet_group_name'],
                StorageType='gp2',
                AllocatedStorage=20,
                LicenseModel='license-included',
                PreferredMaintenanceWindow=MaintenanceWindow,
                ManageMasterUserPassword=True

            )
        else:
            db_inst_class = 'db.r5.large' if context.version.startswith('9.6') else 'db.t3.medium'
            context.rds_client.create_db_instance(
                VpcSecurityGroupIds=config['main']['db_vpc_security_group_name'],
                DBInstanceIdentifier=context.db_identifier,
                Engine=context.engine,
                EngineVersion=context.version,
                Port=int(context.port),
                MasterUsername=context.user,
                # MasterUserPassword=config['behave']['db_master_password'],
                DBInstanceClass=db_inst_class,
                PubliclyAccessible=False,
                DBSubnetGroupName=config['main']['db_subnet_group_name'],
                AllocatedStorage=10,
                PreferredMaintenanceWindow=MaintenanceWindow,
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
        logger.info(f"Database does not exist")
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
        time.sleep(60)

    while True:
        instance_ready = check_instance_running(context)
        if instance_ready:
            break
        time.sleep(60)

    return True


###########
#   BDD
###########
@given("an RDS {database_type} database exists")
def step_impl(context, database_type):
    if database_type == 'SQLServer':
        context.instance_or_cluster = 'instance'
        context.db_identifier = 'mssqlsrvr-validate-8148'
        context.db_cluster_identifier = 'mssqlsrvr-validate-8148'
        context.engine = 'sqlserver-ee'
        context.version = '15.00'
        context.port = '1433'
        context.user = 'supuser'
        context.engine_mode = None
        #
        context.db_list[context.db_identifier] = {'instance_or_cluster': context.instance_or_cluster,
                                                  'cluster_identifier': context.db_cluster_identifier,
                                                  'engine_mode': context.engine_mode}
        setup_test_rds_instance(context)

    elif database_type == 'MySQL':
        context.instance_or_cluster = 'instance'
        context.db_identifier = 'mysql-validate-db'
        context.db_cluster_identifier = 'mysql-validate-db'
        context.engine = 'mysql'
        context.version = '5.7.39'
        context.port = '3306'
        context.user = 'admin'
        context.engine_mode = None
        #
        context.db_list[context.db_identifier] = {'instance_or_cluster': context.instance_or_cluster,
                                                  'cluster_identifier': context.db_cluster_identifier,
                                                  'engine_mode': context.engine_mode}
        setup_test_rds_instance(context)

    elif database_type == 'PostgreSQL':
        context.instance_or_cluster = 'instance'
        context.db_identifier = 'postgres14-validate-db'
        context.db_cluster_identifier = 'postgres14-validate-db'
        context.engine = 'postgres'
        context.version = '14.4'
        context.port = '5432'
        context.user = 'postgres'
        context.engine_mode = None
        #
        context.db_list[context.db_identifier] = {'instance_or_cluster': context.instance_or_cluster,
                                                  'cluster_identifier': context.db_cluster_identifier,
                                                  'engine_mode': context.engine_mode}
        setup_test_rds_instance(context)

    elif database_type == 'Aurora Serverless':
        context.instance_or_cluster = 'cluster'
        context.db_identifier = 'svls-mysql57-validate-db'
        context.db_cluster_identifier = 'svls-mysql57-validate-db'
        context.engine = 'aurora-mysql'
        context.version = '5.7.mysql_aurora.2.07.1'
        context.port = '3306'
        context.user = 'admin'
        context.engine_mode = 'serverless'
        #
        context.db_list[context.db_identifier] = {'instance_or_cluster': context.instance_or_cluster,
                                                  'cluster_identifier': context.db_cluster_identifier,
                                                  'engine_mode': context.engine_mode}
        setup_test_rds_cluster(context)

    elif database_type == 'Aurora Provisioned':
        context.instance_or_cluster = 'cluster'
        context.db_identifier = 'prov-pg12-validate-db-instance-1'
        context.db_cluster_identifier = 'prov-pg12-validate-db'
        context.engine = 'aurora-postgresql'
        context.version = '12.9'
        context.port = '5432'
        context.user = 'postgres'
        context.engine_mode = 'provisioned'
        #
        context.db_list[context.db_identifier] = {'instance_or_cluster': context.instance_or_cluster,
                                                  'cluster_identifier': context.db_cluster_identifier,
                                                  'engine_mode': context.engine_mode}
        setup_test_rds_cluster(context)
    elif database_type == 'OracleServer':
        context.instance_or_cluster = 'instance'
        context.db_identifier = 'test-123-oracle12'
        context.db_cluster_identifier = 'test-123-oracle12'
        context.engine = 'oracle-ee'
        context.version = '19.0'
        context.port = '1521'
        context.user = 'admin'
        context.engine_mode = None
        #
        context.db_list[context.db_identifier] = {'instance_or_cluster': context.instance_or_cluster,
                                                  'cluster_identifier': context.db_cluster_identifier,
                                                  'engine_mode': context.engine_mode}
        setup_test_rds_instance(context)

    else:
        assert False


@when("RDS Audit Log API is invoked")
def step_impl(context):
    with mock.patch('enable_audit_handler.db_created_less_than_1hr') as mock_db_create_time:
        mock_db_create_time.return_value = True

        if context.engine_mode == 'provisioned':
            event_with_auth = {'headers': {'Content-Type': 'application/json'},
                               'body': json.dumps(
                                   dict(account_id=context.test_account,
                                        region=context.region,
                                        instance_or_cluster='instance',
                                        db_identifier=context.db_identifier)
                               )}
        else:
            event_with_auth = {'headers': {'Content-Type': 'application/json'},
                               'body': json.dumps(
                                   dict(account_id=context.test_account,
                                        region=context.region,
                                        instance_or_cluster=context.instance_or_cluster,
                                        db_identifier=context.db_identifier)
                               )}

        if context.bdd_local:
            from enable_audit_handler import handler
            handler_output = handler(event_with_auth, '')
        else:
            url = f'http://{context.api_host}/v1/rdsauditlog'
            headers = (event_with_auth["headers"] if 'headers' in event_with_auth else {})
            body = event_with_auth["body"]
            response = requests.post(url, data=body, headers=headers)

    if context.bdd_local:
        context.lambda_status_code = str(handler_output['statusCode'])
        context.response_body = json.loads(handler_output['body'])
    else:
        context.lambda_status_code = str(response.status_code)
        context.response_body = json.loads(response.text)


@step("the database instance {is_or_is_not} audit log enabled")
@retry(tries=15, delay=2, backoff=1.5)
def step_impl(context, is_or_is_not):
    if is_or_is_not == 'is':
        assert_that('200', equal_to(context.lambda_status_code))
        assert_that('Audit logging has been successfully enabled', equal_to(context.response_body['message']))
    else:
        if context.db_identifier.startswith('sqlserver'):
            logger.info('Modifying SQLServer instance Option Group with default:sqlserver-ex-15-00')
            context.rds_client.modify_db_instance(
                DBInstanceIdentifier=context.db_identifier,
                OptionGroupName='default:sqlserver-ex-15-00',
                ApplyImmediately=True,
            )

        elif context.db_identifier.startswith('mysql'):
            logger.info('Modifying MySQL instance Option Group with default:mysql-5-7')
            context.rds_client.modify_db_instance(
                DBInstanceIdentifier=context.db_identifier,
                OptionGroupName='default:mysql-5-7',
                ApplyImmediately=True,
                CloudwatchLogsExportConfiguration={"DisableLogTypes": ['audit']},
            )
        elif context.db_identifier.startswith('postgres'):
            logger.info('Modifying PostgreSQL instance Parameter Group with default.postgres14')
            context.rds_client.modify_db_instance(
                DBInstanceIdentifier=context.db_identifier,
                DBParameterGroupName='default.postgres14',
                ApplyImmediately=True,
                CloudwatchLogsExportConfiguration={"DisableLogTypes": ["postgresql"]},
            )
        elif context.db_identifier.startswith('svls-mysql57'):
            logger.info('Modifying Aurora Serverless with default.aurora-mysql5.7')
            context.rds_client.modify_db_cluster(
                DBClusterIdentifier=context.db_cluster_identifier,
                DBClusterParameterGroupName='default.aurora-mysql5.7',
            )
        elif context.db_identifier.startswith('prov-'):
            logger.info('Setting Aurora Provisioned Cluster Param Group to default.aurora-postgresql12')
            context.rds_client.modify_db_cluster(
                DBClusterIdentifier=context.db_cluster_identifier,
                DBClusterParameterGroupName='default.aurora-postgresql12',
            )
        else:
            assert False


@step("the instance parameter group is not audit log enabled")
@retry(tries=15, delay=2, backoff=1.5)
def step_impl(context):
    logger.info('Setting Aurora Provisioned Instance Param Group to default.aurora-postgresql12')
    context.rds_client.modify_db_instance(
        DBInstanceIdentifier=context.db_identifier,
        DBParameterGroupName='default.aurora-postgresql12',
        ApplyImmediately=True,
    )


@then("validation Step Function execution begins")
def step_impl(context):
    if 'error' in context.response_body:
        context.lambda_status_message = context.response_body['error']
    # Success message
    elif 'message' in context.response_body and 'sfn_execution_arn' in context.response_body:
        context.lambda_status_message = context.response_body['message']
        context.sfn_execution_arn = context.response_body['sfn_execution_arn']
    else:
        assert False


@step("Step Function is running and invokes validation Lambda")
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


@step("Step Function concludes with status {response_status} and {response_message} message")
def step_impl(context, response_status, response_message):
    sfn_execution_status = json.loads(context.exec_response.get('output', 'failed'))
    logger.info({'final sfn_execution_status': sfn_execution_status})
    assert True if (sfn_execution_status['status'] == response_status and
                    sfn_execution_status['message'] == response_message) else False
