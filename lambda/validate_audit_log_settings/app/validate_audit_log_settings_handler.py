"""
Module to validate audit log settings
"""
import sys
import os
import boto3
from retry import retry

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # app/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../'))  # util/
sys.path.append(THIS_DIR)
sys.path.append(UTIL_DIR)

from util.auth_utilities import Logger
from util import rds_config
from util.client_utilities import ClientUtilities
from exceptions import FailedAuditLogEnableError


def handler(event, context):
    """
    entry function to audit_log_validation
    """
    global logger

    logger_uuid = event.get("logger_uuid")
    logger = Logger()
    logger.set_uuid(id=logger_uuid)

    try:
        return initialize_audit_log_settings(event)
    except Exception as err:
        logger.error(f'Error: {err}')
        return {'status': 'failed', 'message': 'Failure details: ' + str(err)}


@retry(tries=15, delay=2, backoff=1.5)
def initialize_audit_log_settings(event):
    """
    Initializes settings of audit log
    Retry settings gives it a duration of <5m for database to retry before raising an exception
    @param event:
    @return:
    """
    db_type = event.get('db_type')
    db_identifier = event.get('db_identifier')
    db_region = event.get('db_region')
    db_account_id = event.get('db_account_id')

    logger.info(f'Entering validate_audit_log_settings(): Event = {event}')

    # RDS resources will be created in test account
    target_client = ClientUtilities()
    rds_client = target_client.boto3_client(db_account_id, 'rds', db_region)  # Target account client

    sm_client = target_client.boto3_client(db_account_id, 'secretsmanager', db_region)

    #
    # Get DB Instance or Cluster ID
    #
    # DB Cluster: Aurora Serverless
    if db_type == 'cluster':
        logger.info('In db_type == "cluster"')
        dbs_clusters = rds_client.describe_db_clusters(DBClusterIdentifier=db_identifier)
        db_cluster, db_engine, db_engine_version, db_engine_mode = get_cluster_info(dbs_clusters)

        # RETRY here - Check if cluster is in available state before proceeding
        if db_cluster['Status'] != 'available':
            raise FailedAuditLogEnableError('Cluster not \"available\". Current state=' + db_cluster['Status'])

        return initialize_cluster_validation(rds_client, db_cluster, db_engine, db_engine_version, db_engine_mode)

    elif db_type == 'instance':
        # DB Instance: Aurora provisioned and RDS Instance
        logger.info('In db_type == "instance"')
        db_instances = rds_client.describe_db_instances(DBInstanceIdentifier=db_identifier)
        db_instance = db_instances["DBInstances"][0]
        db_engine = db_instance['Engine']
        db_engine = db_engine if not db_engine.startswith('aurora') else 'aurora'
        db_engine_version = db_instance["EngineVersion"]

        # RETRY here - Check if instance is in available state before proceeding
        if db_instance['DBInstanceStatus'] != 'available':
            raise FailedAuditLogEnableError('Instance not \"available\". Current state=' + db_instance['DBInstanceStatus'])

        if db_engine == 'aurora' and 'DBClusterIdentifier' in db_instance:
            db_cluster_id = db_instance.get('DBClusterIdentifier')
            db_cluster, db_engine, db_engine_version, db_engine_mode = get_cluster_info(db_cluster_id)
            return initialize_cluster_validation(rds_client, db_cluster, db_engine, db_engine_version, db_engine_mode)
        else:
            return initialize_instance_validation(rds_client, sm_client, db_account_id, db_region, db_instance,
                                                  db_engine, db_engine_version)
    else:
        logger.info('In "Unknown incoming event"')
        return {"status": "failed", "message": "Unknown incoming event"}


def get_cluster_info(dbs_clusters):
    """
    Gets cluster details
    @param dbs_clusters:
    @return:
    """
    db_cluster = dbs_clusters["DBClusters"][0]
    db_engine = db_cluster["Engine"]
    db_engine_version = db_cluster["EngineVersion"]
    db_engine_mode = db_cluster["EngineMode"]
    return db_cluster, db_engine, db_engine_version, db_engine_mode


# Aurora
def initialize_cluster_validation(rds_client, db_cluster, db_engine, db_engine_version, db_engine_mode):
    """
    Initialize validation of clusters
    @param rds_client:
    @param db_cluster:
    @param db_engine:
    @param db_engine_version:
    @param db_engine_mode:
    @return:
    """
    logger.info('Entered initialize_cluster_validation()')
    try:
        #
        # Aurora MySQL
        if (db_engine in rds_config.MYSQL_FAMILY) and (db_engine_version.startswith("5.")):
            logger.info('In dbEngine=mysql and db_engine_version.startswith("5.")')
            parameters = rds_config.AUDIT_LOG_PARAMS['MYSQL_CLUSTER_FAMILY']
            enable_log_types = ["audit"] if db_engine_mode == "provisioned" else [""]
            return validate_cluster_parameter_groups(rds_client, parameters, db_cluster, enable_log_types,
                                                     db_engine_mode,
                                                     db_engine, db_engine_version)
        #
        # Aurora Postgres
        elif db_engine in rds_config.POSTGRESQL_FAMILY:
            logger.info('In postgres')
            parameters = rds_config.AUDIT_LOG_PARAMS['POSTGRESQL_CLUSTER_FAMILY']
            enable_log_types = ["postgresql"] if db_engine_mode == "provisioned" else [""]
            return validate_cluster_parameter_groups(rds_client, parameters, db_cluster, enable_log_types,
                                                     db_engine_mode,
                                                     db_engine, db_engine_version)
        #
        else:
            return {"status": "failed", "message": "Unsupported engine type"}
    except Exception as err:
        logger.error(f'Error: {err}')
        return {'status': 'failed', 'message': 'Failure details: ' + str(err)}


def validate_cluster_parameter_groups(rds_client, parameters, db_cluster, enable_log_types, db_engine_mode, db_engine,
                                      db_engine_version):
    """
    Fn to validate cluster param group settings
    @param rds_client:
    @param parameters:
    @param db_cluster:
    @param enable_log_types:
    @param db_engine_mode:
    @param db_engine:
    @param db_engine_version:
    @return:
    """
    output = ""

    # Check for CloudwatchLogExport settings. Skip if serverless as logTypes don't apply
    if db_engine_mode != 'serverless' and enable_log_types:
        if "EnabledCloudwatchLogsExports" in db_cluster:
            log_exports = db_cluster["EnabledCloudwatchLogsExports"]
            if not sorted(log_exports) == sorted(enable_log_types):
                return {"status": "failed",
                        "message": f"Validation failed: Log types={enable_log_types} does not match whats enabled"}
            else:
                output += "EnabledCloudwatchLogsExports test: Passed."
        else:
            return {"status": "failed", "message": f"Validation failed: Log types={enable_log_types} not enabled"}

    # Check for Default parameter group name
    """
    If ClusterParameterGroupName == default, newParameterGroupName either does not exist or not applied
    If ClusterParameterGroupName == default, existing Parameter group exists but not applied
    """
    db_cluster_parameter_group_name = db_cluster["DBClusterParameterGroup"]
    if db_cluster_parameter_group_name.startswith("default."):
        logger.info('In db_cluster_parameter_group_name.startswith(default.)')
        return {"status": "failed",
                "message": f"Validation failed: Assigned param group={db_cluster_parameter_group_name} should not be "
                           f"default"}
    else:
        output += "Assigned parameter group \"not default\" test: Passed. "

    # Validate if cluster parameters match
    checked_count = 0
    valid_count = len(parameters)

    # Read all parameters found in clusters Parameter Group Name
    # describe_db_parameters only reads 100 at a time so use marker to read full list into rds_db_parameters
    marker = None
    rds_db_parameters = []
    while True:
        if not marker:
            response = rds_client.describe_db_cluster_parameters(
                DBClusterParameterGroupName=db_cluster_parameter_group_name)
        else:
            response = rds_client.describe_db_cluster_parameters(
                DBClusterParameterGroupName=db_cluster_parameter_group_name,
                Marker=marker)
        rds_db_parameters.extend(response.get('Parameters'))
        marker = response.get('Marker')
        if not marker:
            break

    # Check for matching parameter settings in parameter groups
    for rds_db_parameter in rds_db_parameters:
        for parameter in parameters:
            if rds_db_parameter['ParameterName'] == parameter['ParameterName']:
                # If key 'ParameterValue' does not exist when value set is empty
                if parameter['ParameterValue'] == "" and 'ParameterValue' not in rds_db_parameter:
                    checked_count += 1
                # If key 'ParameterValue' exists and value set is not empty
                if 'ParameterValue' in parameter and 'ParameterValue' in rds_db_parameter and \
                        rds_db_parameter['ParameterValue'] == parameter['ParameterValue']:
                    checked_count += 1
    if checked_count != valid_count:
        return {"status": "failed", "message": f"ClusterParameterSettings test failed with valid count={valid_count} "
                                               f"and checked_count={checked_count}"}
    output += "ClusterParameterSettings test: Passed."

    # if Serverless cluster then it has no members, so return result
    if not db_cluster["DBClusterMembers"]:
        return {"status": "success", "message": output}

    # if Provisioned cluster then validate instances
    for db_cluster_member in db_cluster["DBClusterMembers"]:
        db_instance_id = db_cluster_member["DBInstanceIdentifier"]
        db_cluster_instance = rds_client.describe_db_instances(DBInstanceIdentifier=db_instance_id)["DBInstances"][0]
        logger.info(f'db_instance_identifier = {db_instance_id}, db_cluster_instance = {db_cluster_instance}')
        response = initialize_cluster_instance_validation(rds_client, db_cluster_instance, db_engine, db_engine_version,
                                                          db_engine_mode)
        if response['status'] == 'failed':
            return response

    return {"status": "success", "message": 'cluster and instance validation passed'}


def initialize_cluster_instance_validation(rds_client, db_cluster_instance, db_engine, db_engine_version,
                                           db_engine_mode):
    """
    Fn to initialize cluster instance validation
    @param rds_client:
    @param db_cluster_instance:
    @param db_engine:
    @param db_engine_version:
    @param db_engine_mode:
    @return:
    """
    #
    # MySQL (uses Parameter groups)
    logger.info('Entered initialize_cluster_instance_validation()')
    if (db_engine in rds_config.MYSQL_FAMILY) and (db_engine_version.startswith("5.")):
        logger.info('In dbEngine=mysql and db_engine_version.startswith("5.")')
        parameters = rds_config.AUDIT_LOG_PARAMS['MYSQL_CLUSTER_INSTANCE_FAMILY']
        enable_log_types = ["audit"] if db_engine_mode == "provisioned" else [""]
        return validate_instance_parameter_groups(rds_client, parameters, db_cluster_instance, enable_log_types)
    #
    # Postgres (uses Parameter groups)
    elif db_engine in rds_config.POSTGRESQL_FAMILY:
        logger.info('In dbEngine=postgres')
        parameters = rds_config.AUDIT_LOG_PARAMS['POSTGRESQL_CLUSTER_INSTANCE_FAMILY']
        enable_log_types = ["postgresql"] if db_engine_mode == "provisioned" else [""]
        return validate_instance_parameter_groups(rds_client, parameters, db_cluster_instance, enable_log_types)
    #
    else:
        return {"status": "failed", "message": "Unsupported engine type detected"}


def initialize_instance_validation(rds_client, sm_client, db_account_id, db_region, db_instance, db_engine,
                                   db_engine_version):
    """
    Fn to initialize instance validation
    @param rds_client:
    @param sm_client:
    @param db_account_id:
    @param db_region:
    @param db_instance:
    @param db_engine:
    @param db_engine_version:
    @return:
    """
    logger.info('Entered initialize_instance_validation()')
    # MySQL v5.x and 8.x (uses Option groups)
    if "mysql" in db_engine:
        major, minor = map(str, db_engine_version.split('.')[0:2])
        # For 8.0 engine_versions start from 8.0.11
        if (major == '8' and minor == "0") and (db_engine_version < '8.0.25'):
            return {"status": "failed", "message": "Unsupported engine type detected. MySQL 8.0 version is < 8.0.25"}

        logger.info('In dbEngine=mysql')
        options = rds_config.AUDIT_LOG_PARAMS['MYSQL_OPTIONS']
        enable_log_types = ["audit"]
        return validate_instance_option_groups(rds_client, options, db_instance, enable_log_types)
    #
    # SQLServer (uses Option groups)
    elif "sqlserver" in db_engine:
        logger.info('In dbEngine=sqlserver')

        # get S3 log bucket in account for region
        s3_log_bucket_name = os.environ.get('s3_bucket_log_export', None)
        s3_log_bucket_with_prefix_arn = f'arn:aws:s3:::{s3_log_bucket_name}/AWSLogs/{db_account_id}/rds'
        rds_to_s3_iam_role_name = rds_config.MSSQL_IAM_ROLE_NAME + '-' + db_region
        mssql_iam_role_arn = f"arn:aws:iam::{db_account_id}:role/service-role/{rds_to_s3_iam_role_name}"

        options_to_include = rds_config.AUDIT_LOG_PARAMS['SQLSERVER_OPTIONS']
        enable_log_types = []
        if len(options_to_include) == 1:
            for options in (options_to_include[0]["OptionSettings"]):
                if options['Name'] == 'S3_BUCKET_ARN' and options['Value'] == '':
                    options['Value'] = s3_log_bucket_with_prefix_arn
                if options['Name'] == 'IAM_ROLE_ARN' and options['Value'] == '':
                    options['Value'] = mssql_iam_role_arn
        else:
            raise FailedAuditLogEnableError("Invalid rds_config.MSSQL_FAMILY configuration")

        return validate_instance_option_groups(rds_client, options_to_include, db_instance, enable_log_types)

    #
    # Postgres (uses Parameter groups)
    elif "postgres" in db_engine:
        logger.info('In dbEngine=postgres')
        parameters = rds_config.AUDIT_LOG_PARAMS['POSTGRESQL_INSTANCE_FAMILY']
        enable_log_types = ["postgresql"]
        return validate_instance_parameter_groups(rds_client, parameters, db_instance, enable_log_types)
    #
    # Oracle (uses Parameter groups)
    elif "oracle" in db_engine:
        logger.info('In dbEngine=oracle')
        parameters = rds_config.AUDIT_LOG_PARAMS['ORACLE_INSTANCE_FAMILY']
        enable_log_types = ["audit"]
        res = validate_instance_parameter_groups(rds_client, parameters, db_instance, enable_log_types)
        logger.info('In validate parameter group success')
        if res['status'] == 'failed':
            return res
        options = rds_config.AUDIT_LOG_PARAMS['ORACLE_OPTIONS']
        logger.info('In validate parameter group success')
        return validate_instance_oracle_option_groups(rds_client, options, db_instance, enable_log_types)

    #
    else:
        return {"status": "failed", "message": "Unsupported engine type detected"}


def validate_instance_parameter_groups(rds_client, parameters, db_instance, enable_log_types):
    output = ""

    logger.info('In dbInstance[DBParameterGroups]')

    db_parameter_group_name = db_instance["DBParameterGroups"][0]["DBParameterGroupName"]

    # check for CloudwatchLogExport settings
    if enable_log_types:
        if "EnabledCloudwatchLogsExports" in db_instance:
            log_exports = db_instance["EnabledCloudwatchLogsExports"]
            if not sorted(log_exports) == sorted(enable_log_types):
                return {"status": "failed",
                        "message": f"Validation failed: Log types={enable_log_types} don't match whats enabled"}
            else:
                output += "EnabledCloudwatchLogsExports test: Passed."
        else:
            return {"status": "failed", "message": f"Validation failed: Log types={enable_log_types} not enabled"}

    """
    If ParameterGroupName == default, newParameterGroupName either does not exist or not applied
    If ParameterGroupName == default, existing Parameter group exists but not applied
    """
    # check for default parameter group setting
    if db_parameter_group_name.startswith("default."):
        logger.info('In db_parameter_group_name.startswith(default.)')
        return {"status": "failed",
                "message": f"Validation failed: Assigned param group={db_parameter_group_name} should not be the "
                           f"default"}
    else:
        output += "Assigned parameter group \"not default\" test: Passed. "

    checked_count = 0
    valid_count = len(parameters)

    # describe_db_parameters only reads 100 at a time so use marker to read full list into rds_db_parameters
    marker = None
    rds_db_parameters = []
    while True:
        if not marker:
            response = rds_client.describe_db_parameters(DBParameterGroupName=db_parameter_group_name)
        else:
            response = rds_client.describe_db_parameters(DBParameterGroupName=db_parameter_group_name,
                                                         Marker=marker)
        rds_db_parameters.extend(response.get('Parameters'))
        marker = response.get('Marker')
        if not marker:
            break

    # check for matching parameter settings in parameter groups
    # parameters = parameters[0]['ParameterSettings']
    for rds_db_parameter in rds_db_parameters:
        for parameter in parameters:
            if rds_db_parameter['ParameterName'] == parameter['ParameterName']:
                # If key 'ParameterValue' does not exist when value set is empty
                if parameter['ParameterValue'] == "" and 'ParameterValue' not in rds_db_parameter:
                    checked_count += 1
                # If key 'ParameterValue' exists and value set is not empty
                if 'ParameterValue' in parameter and 'ParameterValue' in rds_db_parameter and \
                        rds_db_parameter['ParameterValue'] == parameter['ParameterValue']:
                    checked_count += 1

    if checked_count == valid_count:
        output += "ParameterSettings test: Passed."
        return {"status": "success", "message": output}
    else:
        output += f"ParameterSettings test failed with valid count={valid_count} and checked_count={checked_count}"
        return {"status": "failed", "message": output}


def validate_instance_option_groups(rds_client, options, db_instance, enable_log_types):
    output = ""
    logger.info('In db_instance["OptionGroupMemberships"]')

    db_option_group_name = db_instance["OptionGroupMemberships"][0]["OptionGroupName"]

    # check for CloudwatchLogExport settings
    if enable_log_types:
        if "EnabledCloudwatchLogsExports" in db_instance:
            log_exports = db_instance["EnabledCloudwatchLogsExports"]
            if not sorted(log_exports) == sorted(enable_log_types):
                return {"status": "failed",
                        "message": f"Validation failed: Log types={enable_log_types} don't match whats enabled"}
            else:
                output += "EnabledCloudwatchLogsExports test: Passed. "
        else:
            return {"status": "failed", "message": f"Validation failed: Log types={enable_log_types} not enabled"}

    """
    If OptionGroupName == default, newOptionGroupName either does not exist or not applied
    If OptionGroupName == default, existing Option group exists but not applied
    """
    # check for default parameter group setting
    if db_option_group_name.startswith("default:"):
        logger.info('In db_option_group_name.startswith("default.")')
        return {"status": "failed",
                "message": f"Validation failed: Assigned options group={db_option_group_name} should not be the "
                           f"default"}
    else:
        output += "Assigned options group \"not default\" test: Passed. "

    # check for matching settings in options group
    option_groups = rds_client.describe_option_groups(OptionGroupName=db_option_group_name)['OptionGroupsList'][0]
    checked_count = 0
    valid_count = 0

    for option in options:
        # valid_count = option['valid_count']
        valid_count = len(option['OptionSettings'])
        for option_group in option_groups['Options']:
            if option_group['OptionName'] == option['OptionName']:
                option_settings = option_group['OptionSettings']
                for option_setting in option_settings:
                    for incoming_option_setting in option['OptionSettings']:
                        if option_setting['Name'] == incoming_option_setting['Name'] and \
                                option_setting['Value'] == incoming_option_setting['Value']:
                            checked_count += 1

    if checked_count == valid_count:
        output += "ParameterSettings test: Passed."
        return {"status": "success", "message": output}
    else:
        output += f"ParameterSettings test failed with valid count={valid_count} and checked_count={checked_count}"
        return {"status": "failed", "message": output}


def validate_instance_oracle_option_groups(rds_client, options, db_instance, enable_log_types):
    output = ""
    logger.info('In db_instance["OptionGroupMemberships"]')

    db_option_group_name = db_instance["OptionGroupMemberships"][0]["OptionGroupName"]

    # check for CloudwatchLogExport settings
    if enable_log_types:
        if "EnabledCloudwatchLogsExports" in db_instance:
            log_exports = db_instance["EnabledCloudwatchLogsExports"]
            if not sorted(log_exports) == sorted(enable_log_types):
                return {"status": "failed",
                        "message": f"Validation failed: Log types={enable_log_types} don't match whats enabled"}
            else:
                output += "EnabledCloudwatchLogsExports test: Passed. "
        else:
            return {"status": "failed", "message": f"Validation failed: Log types={enable_log_types} not enabled"}

    """
    If OptionGroupName == default, newOptionGroupName either does not exist or not applied
    If OptionGroupName == default, existing Option group exists but not applied
    """
    # check for default parameter group setting
    if db_option_group_name.startswith("default:"):
        logger.info('In db_option_group_name.startswith("default.")')
        return {"status": "failed",
                "message": f"Validation failed: Assigned options group={db_option_group_name} should not be the "
                           f"default"}
    else:
        output += "Assigned options group \"not default\" test: Passed. "

    # check for matching settings in options group
    option_groups = rds_client.describe_option_groups(OptionGroupName=db_option_group_name)['OptionGroupsList'][0]
    checked_count = 0
    valid_count = 0

    for option in options:
        if option['OptionName'] == 'S3_INTEGRATION':  # no option settings for oracle
            checked_count += 1
            valid_count += 1
            continue
        valid_count += len(option['OptionSettings'])
        for option_group in option_groups['Options']:
            if option_group['OptionName'] == option['OptionName']:
                option_settings = option_group['OptionSettings']
                for option_setting in option_settings:
                    for incoming_option_setting in option['OptionSettings']:
                        if option_setting['Name'] == incoming_option_setting['Name'] and \
                                option_setting['Value'] == incoming_option_setting['Value']:
                            checked_count += 1

    if checked_count == valid_count:
        output += "ParameterSettings test: Passed."
        return {"status": "success", "message": output}
    else:
        output += f"ParameterSettings test failed with valid count={valid_count} and checked_count={checked_count}"
        return {"status": "failed", "message": output}


def boto3_client(region, service):
    rds_client = boto3.client(
        region_name=region,
        service_name=service,
    )
    return rds_client
