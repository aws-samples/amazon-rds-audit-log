"""
Utilities to enable audit logging for RDS instances
"""
import json
import string
import os
import sys
import platform
import jinja2
import time
import psycopg2
import pyodbc
import cx_Oracle
from botocore.exceptions import ClientError
from retry import retry

THIS_DIR = os.path.dirname(os.path.realpath(__file__))
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../util'))  # util/
sys.path.append(UTIL_DIR)
import rds_config
from exceptions import InvalidInputError, InvalidDataOrConfigurationError, FailedAuditLogEnableError


def set_log_types_db_instance(rds_client,
                              iam_client,
                              project_id,
                              region,
                              db_instance,
                              logger,
                              db_user=None,
                              db_password=None,
                              apply_immediately=True,
                              lambda_client=None):
    """
    function to set log_types depending on DB Engine
    @param rds_client:
    @param iam_client:
    @param project_id:
    @param region:
    @param db_instance:
    @param logger:
    @param db_user:
    @param db_password:
    @param apply_immediately:
    @param lambda_client:
    @return:
    """
    logger.info('Entering set_log_types_db_instance()')

    db_engine = db_instance["Engine"]
    db_engine_version = db_instance["EngineVersion"]
    db_instance_identifier = db_instance["DBInstanceIdentifier"]
    db_apply_immediate = bool(apply_immediately)

    if not (db_engine and db_engine_version and db_instance_identifier and str(db_apply_immediate)):
        raise InvalidInputError("Empty values found: 'db_engine' or 'db_engine_version' or 'db_instance_identifier' or "
                                "'db_apply_immediate' or all")

    # Convert full to major version (15.00.344 to 15.00)
    temp = db_engine_version.split(".")
    db_major_version = "%s.%s" % (temp[0], temp[1])
    major, minor = map(str, db_engine_version.split('.')[0:2])

    # MySQL v5.x and 8.x (uses Option groups)
    if db_engine in rds_config.MYSQL_FAMILY:
        # For 8.0 engine_versions start from 8.0.11
        if (major == '8' and minor == "0") and (db_engine_version < '8.0.25'):
            raise InvalidInputError("Unsupported engine type detected. MySQL 8.0 version < 8.0.25")
        logger.info('In db_engine=mysql')
        enable_log_types = ["audit"]
        option_group_changes(
            logger,
            rds_client,
            db_instance,
            db_engine,
            db_major_version,
            db_instance_identifier,
            enable_log_types,
            apply_immediately=db_apply_immediate,
        )
    #
    # MS-SQL Server (uses Option groups)
    elif db_engine in rds_config.MSSQL_FAMILY:
        logger.info('In db_engine=sqlserver')

        rds_to_s3_iam_role_arn, s3_log_bucket_with_prefix_arn = get_s3logbucket_and_role(logger, project_id, iam_client,
                                                                                         region)
        rds_config.MSSQL_S3_BUCKET_ARN = s3_log_bucket_with_prefix_arn
        rds_config.MSSQL_IAM_ROLE_ARN = rds_to_s3_iam_role_arn

        # Enable Option Group to set Audit Logs. Apply=true enables SQLServer Audit logs else scripts won't run
        enable_log_types = []
        option_group_changes(logger, rds_client, db_instance, db_engine, db_major_version, db_instance_identifier,
                             enable_log_types, apply_immediately=True)

        # Enable Parameter Group to enforce TLS 1.2
        instance_parameter_group_changes(logger, rds_client, db_instance, db_engine, major, minor,
                                         db_instance_identifier, enable_log_types=enable_log_types,
                                         apply_immediately=db_apply_immediate)

        # Transition from Available > Modifying > Available
        logger.info('Wait for Option/Parameter group changes to take effect and for instance to go to Modifying state')
        check_instance_state(logger, rds_client, db_instance_identifier, 'modifying')

        logger.info('Waiting for instance to be in Available state with Audit Log enabled, before running SQL cmds')
        waiter = rds_client.get_waiter('db_instance_available')
        waiter.wait(DBInstanceIdentifier=db_instance_identifier)

        # Run SQL cmds
        sql_server_run_sql_cmds(logger, host=db_instance["Endpoint"]['Address'], user=db_user, pwd=db_password)
        # Enable Option Group
        enable_log_types = []
        option_group_changes(
            logger,
            rds_client,
            db_instance,
            db_engine,
            db_major_version,
            db_instance_identifier,
            enable_log_types,
            apply_immediately=db_apply_immediate,
        )
    #
    # MySQL v8+ only (uses Param groups)
    elif (db_engine in rds_config.MYSQL_FAMILY) and (db_engine_version.startswith("8.")):
        logger.info('In db_engine=mysql and db_engine_version.startswith("8.")')
        enable_log_types = ["general", "slowquery"]
        instance_parameter_group_changes(logger, rds_client, db_instance, db_engine, major, minor,
                                         db_instance_identifier, enable_log_types=enable_log_types,
                                         apply_immediately=db_apply_immediate)
    #
    # Postgres (uses Param groups)
    elif db_engine in rds_config.POSTGRESQL_FAMILY:
        logger.info('In db_engine=postgres')
        # Run SQL cmds
        postgresql_server_run_sql_cmds(
            logger,
            host=db_instance["Endpoint"]['Address'],
            user=db_user,
            pwd=db_password,
        )
        # Enable Parameter Group
        enable_log_types = ["postgresql"]
        instance_parameter_group_changes(logger, rds_client, db_instance, db_engine, major, minor,
                                         db_instance_identifier, enable_log_types=enable_log_types,
                                         apply_immediately=db_apply_immediate)
    #
    # Oracle (uses Param groups)
    elif db_engine in rds_config.ORACLE_FAMILY or db_engine in 'oracle-se2':
        logger.info('In db_engine=oracle')
        if db_instance['DBName']:
            db_name = db_instance['DBName']
        else:
            db_name = 'ORCL'
        event_dict = {"db_name": db_name, "host": db_instance["Endpoint"]['Address'], "db_user": db_user,
                      "db_password": db_password,
                      "db_major_version": db_major_version, 'uuid': logger._id}

        # db_major_version = '19.0' #if db_major_version.startswith('19') else '12.2'
        #  Run SQL cmds
        logger.info("invoking lambda for sql commands")
        response = lambda_client.invoke(
            FunctionName=os.environ.get('oracle_lambda_func', None),
            InvocationType='RequestResponse',
            Payload=json.dumps(event_dict).encode('utf-8')
        )
        logger.info(f"lambda for sql commands response {response}")
        t = response['Payload']
        j = t.read()
        response = json.loads(j)
        if response['statusCode'] != 200:
            raise FailedAuditLogEnableError(response['body'])

        # Enable Parameter Group
        enable_log_types = ["audit"]
        instance_parameter_group_changes(logger, rds_client, db_instance, db_engine, major, minor,
                                         db_instance_identifier, enable_log_types=enable_log_types,
                                         apply_immediately=db_apply_immediate)
        option_group_engine = major if db_major_version.startswith('19') else db_major_version
        option_group_changes(
            logger,
            rds_client,
            db_instance,
            db_engine,
            option_group_engine,
            db_instance_identifier,
            enable_log_types,
            apply_immediately=db_apply_immediate,
        )
    else:
        raise InvalidDataOrConfigurationError('enable_mssql_handler > logTypes_db_instance: unsupported engine type')

    logger.info('Exiting set_log_types_db_instance()')


@retry(tries=15, delay=2, backoff=1.5)
def check_instance_state(logger, rds_client, db_identifier, desired_state):
    response = rds_client.describe_db_instances(DBInstanceIdentifier=db_identifier)
    current_state = response['DBInstances'][0]['DBInstanceStatus']
    if current_state != desired_state:
        raise FailedAuditLogEnableError(f'Instance not in state={desired_state}. Current state={current_state}')
    else:
        logger.info(f'Instance: {db_identifier} in state={desired_state}. Proceeding')


# Return S3 Log Bucket for Account in Region and RDS-S3-Role
def get_s3logbucket_and_role(logger, project_id, iam_client, region):
    # Get S3 Log bucket for account in region
    s3_log_bucket_name = os.environ.get('s3_bucket_log_export', None)
    s3_log_bucket_arn = f'arn:aws:s3:::{s3_log_bucket_name}'
    s3_log_bucket_with_prefix_arn = f'arn:aws:s3:::{s3_log_bucket_name}/AWSLogs/{project_id}/rds'
    rds_to_s3_iam_role_name = rds_config.MSSQL_IAM_ROLE_NAME + '-' + region

    # Create RDS to S3 role if not exists
    if iam_role_exists(logger, iam_client, rds_to_s3_iam_role_name):
        logger.info(f'RDS-to-S3 Role exists. Role={rds_to_s3_iam_role_name}')
        rds_to_s3_iam_role_arn = get_iam_role_for_rds_to_s3(logger, iam_client, rds_to_s3_iam_role_name)
    else:
        logger.info(f'Creating RDS-to-S3 Role={rds_to_s3_iam_role_name}')
        rds_to_s3_iam_role_arn = create_iam_role_for_rds_to_s3(logger, rds_to_s3_iam_role_name, iam_client,
                                                               s3_log_bucket_arn, s3_log_bucket_with_prefix_arn)
    if rds_to_s3_iam_role_arn is None:
        logger.error(f'Error getting RDS-to-S3 Role ARN. Role={rds_to_s3_iam_role_name}')
        raise FailedAuditLogEnableError(f'Error getting RDS-to-S3 Role ARN. Role={rds_to_s3_iam_role_name}')
    return rds_to_s3_iam_role_arn, s3_log_bucket_with_prefix_arn


# Check if RDS-to-S3 IAM role exists
def iam_role_exists(logger, iam_client, rds_to_s3_iam_role_name):
    """Check if the specified IAM role exists
    :param logger: logger client
    :param iam_client: IAM client
    :param rds_to_s3_iam_role_name: IAM role name
    :return: True if IAM role exists, else False
    """
    # Get ARN of specified role to confirm if it exists
    if get_iam_role_for_rds_to_s3(logger, iam_client, rds_to_s3_iam_role_name) is None:
        return False
    return True


# Get RDS-to-S3 IAM role
def get_iam_role_for_rds_to_s3(logger, iam_client, iam_role_name):
    try:
        result = iam_client.get_role(RoleName=iam_role_name)
    except iam_client.exceptions.NoSuchEntityException as e:
        logger.error(f'IAM Role {iam_role_name} does not exist. Exception={e}')
        return None
    except ClientError as e:
        logger.error(f'ClientError on role {iam_role_name}. Error={e}')
        return None
    except Exception as e:
        logger.error(e)
        return None
    return result['Role']['Arn']


# Create RDS-to-S3 IAM role
def create_iam_role_for_rds_to_s3(logger, iam_role_name, iam_client, s3_log_bucket_arn, s3_log_bucket_with_prefix_arn):
    rds_assume_role = {
        'Version': '2012-10-17',
        'Statement': [
            {
                'Sid': '',
                'Effect': 'Allow',
                'Principal': {
                    'Service': 'rds.amazonaws.com'
                },
                'Action': 'sts:AssumeRole'
            }
        ]
    }

    try:
        result = iam_client.create_role(RoleName=iam_role_name,
                                        Path='/service-role/',
                                        AssumeRolePolicyDocument=json.dumps(rds_assume_role))
        logger.info(f'Created RDS-to-S3 Role={iam_role_name}')
    except ClientError as err:
        logger.error(f'Error creating RDS-to-S3 Role={iam_role_name}. Error={err}')
        return None
    except Exception as err:
        logger.error(f'Error creating RDS-to-S3 Role={iam_role_name}. Error={err}')
        return None

    # Wait till role exists
    waiter = iam_client.get_waiter('role_exists')
    waiter.wait(RoleName=iam_role_name)

    rds_to_s3_role_arn = result['Role']['Arn']

    # Policy for S3 permissions
    policy_name = 'rds_s3_access'
    s3_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "s3:ListAllMyBuckets",
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetBucketLocation",
                    "s3:GetBucketACL",
                    "s3:ListBucket"
                ],
                "Resource": [
                    f"{s3_log_bucket_arn}"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:ListMultipartUploadParts",
                    "s3:AbortMultipartUpload"
                ],
                "Resource": [
                    f"{s3_log_bucket_with_prefix_arn}/*"
                ]
            },
        ]
    }

    try:
        iam_client.put_role_policy(RoleName=iam_role_name,
                                   PolicyName=policy_name,
                                   PolicyDocument=json.dumps(s3_policy))
        logger.info(f'Success inserting policy in RDS-to-S3 Role={iam_role_name}')
    except ClientError as err:
        logger.error(f'Error inserting policy in RDS-to-S3 Role={iam_role_name}. Error={err}')
        return None

    # Need wait for role to be functional for use in SQLSERVER_AUDIT options group
    logger.info(f'Waiting 10s till IAM Role {iam_role_name} is available')
    time.sleep(10)

    # Return the ARN of the created IAM role
    logger.info(f'Success: Created RDS-to-S3 Role={iam_role_name} and inserted Policy={policy_name}')
    return rds_to_s3_role_arn


# Start Instance Parameter Group changes
def instance_parameter_group_changes(logger, rds_client, db_instance, db_engine, major, minor, db_instance_identifier,
                                     enable_log_types=None, is_cluster=False, apply_immediately=True):
    """
    function to initialize rules associated with DB Engine
    @param is_cluster:
    @param logger:
    @param rds_client:
    @param db_instance:
    @param db_engine:
    @param major:
    @param minor:
    @param db_instance_identifier:
    @param enable_log_types:
    @param apply_immediately:
    @return:
    """
    logger.info('Entering instance_parameter_group_changes()')

    parameter_group_names = [
        parameter_group["DBParameterGroupName"]
        for parameter_group in rds_client.describe_db_parameter_groups()["DBParameterGroups"]
    ]

    logger.info('In db_instance[DBParameterGroups]')
    db_parameter_group_name = db_instance["DBParameterGroups"][0]["DBParameterGroupName"]

    # create custom instance parameter group name
    db_name = db_instance["DBInstanceIdentifier"]
    new_parameter_group_name = (
            valid_file_name_creator(db_name)
            + "-" + db_engine + "-" + major + "-" + minor
    )

    ###
    # IF db_parameter_group_name == default., new_parameter_group_name does not exist, create+update new group
    # IF db_parameter_group_name == default., new_parameter_group_name exists, update Parameter group
    # IF db_parameter_group_name != default., update existing Parameter group with audit parameters
    ###
    if db_parameter_group_name.startswith("default."):
        logger.info('In db_parameter_group_name.startswith(default.)')
        if new_parameter_group_name not in parameter_group_names:
            # create new_parameter_group_name and assign params
            modify_instance_parameter_groups(logger, rds_client, "create", db_engine, major, minor,
                                             new_parameter_group_name, is_cluster, db_parameter_group_name)
        # update new_parameter_group_name and assign params
        modify_instance_parameter_groups(logger, rds_client, "update", db_engine, major, minor,
                                         new_parameter_group_name, is_cluster)
        db_parameter_group_name = new_parameter_group_name
    else:
        logger.info('db_parameter_group_name does not startswith(default.)')
        # update existing db_parameter_group_name and assign params
        modify_instance_parameter_groups(logger, rds_client, "update", db_engine, major, minor,
                                         db_parameter_group_name, is_cluster)

    modify_db_instance_parameter_group(logger, rds_client, db_instance_identifier, db_parameter_group_name,
                                       apply_immediately, enable_log_types)

    logger.info('Exiting instance_parameter_group_changes()')


@retry(tries=15, delay=2, backoff=1.5)
def modify_db_instance_parameter_group(logger, rds_client, db_instance_identifier, db_parameter_group_name,
                                       apply_immediately,
                                       enable_log_types):
    """
    Function to modify database instance param groups based on log_types
    Retry settings provides a duration sufficient for database to be available before raising an exception
    @param logger:
    @param rds_client:
    @param db_instance_identifier:
    @param db_parameter_group_name:
    @param apply_immediately:
    @param enable_log_types:
    @return:
    """
    logger.info('Entering modify_db_instance_parameter_group()')

    if enable_log_types is not None:
        logger.info('rds_client.modify_db_instance_parameter_group with enable_log_types != None')
        rds_client.modify_db_instance(
            DBInstanceIdentifier=db_instance_identifier,
            DBParameterGroupName=db_parameter_group_name,
            ApplyImmediately=apply_immediately,
            CloudwatchLogsExportConfiguration={
                "EnableLogTypes": enable_log_types
            },
        )
    else:
        logger.info('rds_client.modify_db_instance with enable_log_types == None')
        rds_client.modify_db_instance(
            DBInstanceIdentifier=db_instance_identifier,
            DBParameterGroupName=db_parameter_group_name,
            ApplyImmediately=apply_immediately,
        )


def get_instance_parameter_group_family(logger, parameter_group_name, db_engine, default_parameter_group_name, major,
                                        minor, rds_client, task):
    """
    function to return instance parameter group family
    @param logger:
    @param parameter_group_name:
    @param db_engine:
    @param default_parameter_group_name:
    @param major:
    @param minor:
    @param rds_client:
    @param task:
    @return:
    """
    logger.info('Entering get_instance_parameter_group_family')
    if db_engine in ['aurora-postgresql', 'postgres', 'oracle-ee', 'oracle-se2'] or \
            db_engine in rds_config.MSSQL_FAMILY:
        # During 'create' use default_cluster_parameter_group else use existing or newly created group name
        if default_parameter_group_name and task == 'create':
            param_group_response = rds_client.describe_db_parameter_groups(
                DBParameterGroupName=default_parameter_group_name)
        else:
            param_group_response = rds_client.describe_db_parameter_groups(
                DBParameterGroupName=parameter_group_name)
        if not param_group_response.get('DBParameterGroups'):
            instance_parameter_group_family = db_engine + major
        else:
            instance_parameter_group_family = param_group_response['DBParameterGroups'][0]['DBParameterGroupFamily']
    # mysql
    else:
        instance_parameter_group_family = db_engine + major + '.' + minor[0]
    logger.info(f'instance_parameter_group_family = {instance_parameter_group_family}')

    return instance_parameter_group_family


def modify_instance_parameter_groups(logger, rds_client, task, db_engine, major, minor, parameter_group_name,
                                     is_cluster, default_parameter_group_name=None):
    """
    function to set instance parameters based on engine type
    @param logger:
    @param rds_client:
    @param task:
    @param db_engine:
    @param major:
    @param minor:
    @param parameter_group_name:
    @param default_parameter_group_name:
    @return:
    """
    logger.info('Entering modify_instance_parameter_groups()')

    description = "For %s %s.%s audit logging" % (db_engine, major, minor)

    # Get instance param group family
    parameter_group_family = get_instance_parameter_group_family(logger, parameter_group_name, db_engine,
                                                                 default_parameter_group_name, major,
                                                                 minor, rds_client, task)
    #
    # Engine= MySQL. Applies to both Aurora cluster and RDS instances
    #
    if db_engine in rds_config.MYSQL_FAMILY:
        logger.info('In db_engine="mysql"')
        if is_cluster:
            parameters = rds_config.AUDIT_LOG_PARAMS['MYSQL_CLUSTER_INSTANCE_FAMILY']
        else:
            parameters = rds_config.AUDIT_LOG_PARAMS['MYSQL_INSTANCE_FAMILY']
    #
    # Engine= Postgres. Applies to both Aurora cluster and RDS instances
    #
    elif db_engine in rds_config.POSTGRESQL_FAMILY:
        logger.info('In "postgres" in db_engine')
        if is_cluster:
            parameters = rds_config.AUDIT_LOG_PARAMS['POSTGRESQL_CLUSTER_INSTANCE_FAMILY']
        else:
            parameters = rds_config.AUDIT_LOG_PARAMS['POSTGRESQL_INSTANCE_FAMILY']

            # add ssl parameter for Postgres database instance whose engine version is less than 14
            if int(major) < 14:
                ssl_param = {
                    "ParameterName": "ssl",
                    "ParameterValue": "1",
                    "ApplyMethod": "immediate",
                }
                parameters.append(ssl_param)
    # Engine= MS-SQLSERVER. Instance only
    #
    elif db_engine in rds_config.MSSQL_FAMILY:
        logger.info('In db_engine in rds_config.MSSQL_FAMILY')
        parameters = rds_config.AUDIT_LOG_PARAMS['SQLSERVER_INSTANCE_FAMILY']
    elif db_engine in rds_config.ORACLE_FAMILY or db_engine in "'oracle-se2":
        logger.info('In "oracle" in db_engine')
        parameters = rds_config.AUDIT_LOG_PARAMS['ORACLE_INSTANCE_FAMILY']
    else:
        raise FailedAuditLogEnableError('modify_instance_parameter_groups: unsupported engine type')

    create_modify_parameter_groups(logger, rds_client, task, parameter_group_name, parameter_group_family, parameters,
                                   description)

    logger.info('Exiting modify_instance_parameter_groups()')


@retry(tries=15, delay=2, backoff=1.5)
def create_modify_parameter_groups(logger, rds_client, task, parameter_group_name, parameter_group_family, parameters,
                                   description):
    """
    Function to create or modify database param group
    Retry settings provides a duration sufficient for database to be available before raising an exception
    @param logger:
    @param rds_client:
    @param task:
    @param parameter_group_name:
    @param parameter_group_family:
    @param parameters:
    @param description:
    @return:
    """
    logger.info('Entering create_modify_parameter_groups()')
    if task == "create":
        logger.info('In task == "create" for rds_client.create_db_parameter_group')
        # Create RDS Option Group
        rds_client.create_db_parameter_group(
            DBParameterGroupName=parameter_group_name,
            DBParameterGroupFamily=parameter_group_family,
            Description=description,
        )
    if task in ["create", "update"]:
        logger.info('In task=="create" or task=="update" for rds_client.create_db_parameter_group')
        # Add options to RDS Option Group
        rds_client.modify_db_parameter_group(
            DBParameterGroupName=parameter_group_name,
            Parameters=parameters
        )
    logger.info('Exiting create_modify_parameter_groups()')


# Start Option Group changes
def option_group_changes(logger, rds_client, db_instance, db_engine, db_major_version, db_instance_identifier,
                         enable_log_types, apply_immediately=True):
    """
    function to apply option group changes
    @param logger:
    @param rds_client:
    @param db_instance:
    @param db_engine:
    @param db_major_version:
    @param db_instance_identifier:
    @param enable_log_types:
    @param apply_immediately:
    @return:
    """
    logger.info('Entering option_group_changes()')

    logger.info('In task=create')
    option_group_names = [
        option_group["OptionGroupName"]
        for option_group in rds_client.describe_option_groups()["OptionGroupsList"]
    ]

    if db_instance["OptionGroupMemberships"]:
        logger.info('In db_instance["OptionGroupMemberships"]')

        option_group_name = db_instance["OptionGroupMemberships"][0]["OptionGroupName"]

        # create custom option group name
        new_option_group_name = "audit-log-" + db_engine + "-" + db_major_version.replace(".", "-")

        ###
        # If OptionGroupName == default, new_option_group_name does not exist, create+update newOptionGroup
        # If OptionGroupName == default, new_option_group_name exists, update DB with newOptionGroup
        # If OptionGroupName != default, update existing Option group with audit plugin
        ###
        if option_group_name.startswith("default:"):
            logger.info('In option_group_name.startswith("default:")')

            if new_option_group_name not in option_group_names:
                # create new_option_group_name and assign audit plugin
                modify_option_groups(logger, rds_client, "create", db_engine, db_major_version, new_option_group_name)

            # update new_parameter_group_name and assign params
            modify_option_groups(logger, rds_client, "update", db_engine, db_major_version, new_option_group_name)

            option_group_name = new_option_group_name
        else:
            logger.info('Not in option_group_name.startswith("default:")')

            # update option_group_name with audit plugin
            modify_option_groups(logger, rds_client, "update", db_engine, db_major_version, option_group_name)

        # assign option_group_name and LogTypes to DB
        modify_db_instance_option_group(logger, rds_client, db_instance_identifier, option_group_name,
                                        apply_immediately, enable_log_types)

    logger.info('Exiting option_group_changes()')


@retry(tries=15, delay=2, backoff=1.5)
def modify_db_instance_option_group(logger, rds_client, db_instance_identifier, option_group_name, apply_immediately,
                                    enable_log_types):
    """
    Function to modify db instance with backoff/retry on exception
    Retry settings provides a duration sufficient for database to be available before raising an exception
    @param logger:
    @param rds_client:
    @param db_instance_identifier:
    @param option_group_name:
    @param apply_immediately:
    @param enable_log_types:
    @return:
    """
    logger.info('Entering modify_db_instance_option_group()')
    rds_client.modify_db_instance(
        DBInstanceIdentifier=db_instance_identifier,
        OptionGroupName=option_group_name,
        ApplyImmediately=apply_immediately,
        CloudwatchLogsExportConfiguration={"EnableLogTypes": enable_log_types},
    )
    logger.info('Exiting modify_db_instance_option_group()')


# Options Groups - Create or Update
def modify_option_groups(logger, rds_client, task, db_engine, db_major_version, option_group_name):
    """
    function to apply option group changes
    @param logger:
    @param rds_client:
    @param task:
    @param db_engine:
    @param db_major_version:
    @param option_group_name:
    @return:
    """
    logger.info('Entering modify_option_groups()')

    options_to_include = {}
    if db_engine in rds_config.MYSQL_FAMILY:
        logger.info('In db_engine=mysql')
        options_to_include = rds_config.AUDIT_LOG_PARAMS['MYSQL_OPTIONS']

    if db_engine in rds_config.MSSQL_FAMILY:
        logger.info('In db_engine=sqlserver')
        options_to_include = rds_config.AUDIT_LOG_PARAMS['SQLSERVER_OPTIONS']
        if len(options_to_include) == 1:
            for options in (options_to_include[0]["OptionSettings"]):
                if options['Name'] == 'S3_BUCKET_ARN' and options['Value'] == '':
                    options['Value'] = rds_config.MSSQL_S3_BUCKET_ARN
                if options['Name'] == 'IAM_ROLE_ARN' and options['Value'] == '':
                    options['Value'] = rds_config.MSSQL_IAM_ROLE_ARN
        else:
            raise FailedAuditLogEnableError("Invalid rds_config.MSSQL_FAMILY configuration")

    if db_engine in rds_config.ORACLE_FAMILY or db_engine in "'oracle-se2'":
        logger.info('In db_engine=ORACLE_FAMILY')
        options_to_include = rds_config.AUDIT_LOG_PARAMS['ORACLE_OPTIONS']

    description = "For %s %s audit logging" % (db_engine, db_major_version)

    create_or_update_option_groups(logger, rds_client, task, option_group_name, options_to_include, True, db_engine,
                                   db_major_version, description)

    logger.info('Exiting modify_option_groups()')


@retry(tries=15, delay=2, backoff=1.5)
def create_or_update_option_groups(logger, rds_client, task, option_group_name, options_to_include, apply_immediately,
                                   db_engine, db_major_version, description):
    """
    Function to create or modify option group changes
    Retry settings provides a duration sufficient for database to be available before raising an exception
    @param logger:
    @param rds_client:
    @param task:
    @param option_group_name:
    @param options_to_include:
    @param apply_immediately:
    @param db_engine:
    @param db_major_version:
    @param description:
    @return:
    """
    logger.info('Entering create_or_update_option_groups()')
    if task == "create":
        logger.info('In task=create')
        # Create RDS Option Group
        rds_client.create_option_group(
            OptionGroupName=option_group_name,
            OptionGroupDescription=description,
            EngineName=db_engine,
            MajorEngineVersion=db_major_version,
        )
    if task in ["create", "update"]:
        logger.info('In task=create or update')
        # Add options to RDS Option Group
        rds_client.modify_option_group(
            OptionGroupName=option_group_name,
            OptionsToInclude=options_to_include,
            ApplyImmediately=apply_immediately,
        )
    logger.info('Exiting create_or_update_option_groups()')


#
# Compliant file name creator
#
def valid_file_name_creator(file_name):
    """
    creates file name compliant with rules from database name input
    : description: below is the sequence in which a given file_name is cleaned up and returned valid
    001_aurora_prov_mysql57--1 > 001auroraprovmysql57--1 > 001auroraprovmysql57-1 > 'auroraprovmysql57-1'
    :param file_name:
    :return:
    """
    # Name identifier must contain only ASCII letters, digits, and hyphens;
    valid_set = {*set(string.ascii_letters), *set(string.digits), "-"}
    file_name = "".join(filter(lambda x: x in valid_set, file_name))
    # Name identifier must not contain two consecutive hyphens
    file_name = file_name.replace("--", "-")
    # Name identifier must not end with a hyphen
    file_name = file_name[:-1] if file_name.endswith("-") else file_name
    # Name identifier must begin with a letter
    invalid_set_of_leading_chars = " ".join([*set(string.punctuation), *set(string.digits)])
    file_name = file_name.lstrip(invalid_set_of_leading_chars)
    return file_name


#
# SQL Cmds and Helper fns
#
def render_sql(logger, sql_file, engine_type, kwargs=None):
    """
    Renders the sql file located in the path ./sql/<engine>/<sql_file>

    Args
        sql_file (str): The sql file name.
        engine_type (str): The engine type; e.g. sqlserver
        kwargs: Keyword arguments.

    Returns:
        str: Blank string if the file or directory cannot be found, sql
        statement as a string otherwise.
    """
    logger.info('Entering render_sql()')

    if not kwargs:
        kwargs = {}
    this_dir = os.path.dirname(__file__)
    try:
        f = open(os.path.join(this_dir, 'sql', engine_type, sql_file))
    except Exception as err:  # pylint: disable=broad-except
        print(f'render_sql() exception: {err}')
        return ''

    raw = f.read()
    t = jinja2.Template(raw)
    result = t.render(**kwargs)

    logger.info('Exiting render_sql()')

    return result


# Postgres SQL execution
def postgresql_server_run_sql_cmds(logger, host, user, pwd):
    """
    Runs the SQL files on the server
    :param logger:
    :param host:
    :param user:
    :param pwd:
    :return:
    """
    logger.info('Entering postgresql_server_run_sql_cmds()')

    database_name = "postgres"

    logger.info(f'Connecting.. database={database_name}, user={user}, password=***, host={host}')
    conn = psycopg2.connect(
        database=database_name,
        user=user,
        password=pwd,
        host=host,
    )
    conn.autocommit = True
    csr = conn.cursor()

    files = ['create-role.sql', 'create-extension.sql']

    for file in files:
        try:
            sql = render_sql(logger, file, 'postgres')
            if not sql:
                continue
            csr.execute(sql)
            logger.info(f'Executed SQL: {sql}')
        except Exception as err:  # pylint: disable=broad-except
            logger.error(f'Exception: {err}')
            continue

    logger.info('Exiting postgresql_server_run_sql_cmds()')


#
# SQL Server SQL execution
#
def sql_server_run_sql_cmds(logger, host, user, pwd, port=1433):
    """
    Runs the SQL files on the server
    :param logger:
    :param host:
    :param user:
    :param pwd:
    :param port:
    :return:
    """
    db = "master"
    logger.info(f'Connecting.. database={db}, user={user}, password=***, host={host}')
    try:
        if platform.system() == "Windows":
            connstr = (
                f"DRIVER={{SQL Server}};SERVER={host},{port};"
                f"DATABASE={db};UID={user};PWD={pwd};"
            )
        else:
            if db:
                connstr = (
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host},{port};"
                    f"DB={db};UID={user};PWD={pwd};"
                )
            else:
                connstr = (
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={host},{port};"
                    f"UID={user};PWD={pwd};"
                )

        conn = pyodbc.connect(connstr, autocommit=True)
        csr = conn.cursor()

        files = ['configure-server-audit.sql',
                 'configure-server-level-audit-spec.sql',
                 'configure-database-level-audit-spec.sql',
                 'create-s3-events-job-and-add-audit-to-new-dbs.sql']

        for file in files:
            try:
                sql = render_sql(logger, file, 'sqlserver')
                if not sql:
                    continue
                csr.execute(sql)
                print("Executed: ", sql)
            except Exception as err:  # pylint: disable=broad-except
                print("Exception: ", err)
                continue
    except Exception as err:
        logger.error(f"connecting {host}:{port} exception: {err}")
        raise InvalidDataOrConfigurationError(str(err))


#
# Oracle SQL execution
#
def oracle_server_run_sql_cmds(logger, host, user, pwd, db_name, db_engine_version, port=1521):
    """
    Runs the SQL files on the server
    :param logger:
    :param host:
    :param user:
    :param pwd:
    :param db_name:
    :param db_engine_version:
    :param port:
    :return:
    """
    logger.info('Entering oracle_server_run_sql_cmds()')
    try:
        logger.info(f'Connecting.. database={db_name}, user={user}, password=***, host={host}')
        dsn = cx_Oracle.makedsn(host, port, db_name)
        conn = cx_Oracle.connect(user, pwd, dsn)
        csr = conn.cursor()

        kwargs = {'VERSION': db_engine_version, 'MASTER_USERNAME': user}
        sql_query = render_sql(logger, 'set-audit-parameters.sql', 'oracle', kwargs=kwargs)

        sql_statement_list = []
        for sql in sql_query.split("\n"):
            if sql:
                sql_statement_list.append(sql)

        for sql_statement in sql_statement_list:
            try:
                csr.execute(sql_statement)
                print('set audit parameters for RDS Database {} for sql {}'.format(host, sql_statement))
            except Exception as err:  # pylint: disable=broad-except
                print(
                    f'Error while setting audit parameters for RDS Database={host}, SQL={sql_statement}. Details={err}')

    except Exception as err:
        logger.error(f"connecting {host}:{port} exception: {err}")
        raise InvalidDataOrConfigurationError(str(err))

    logger.info('Exiting oracle_server_run_sql_cmds()')
