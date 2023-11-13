"""
Utilities to enable audit logging for Aurora Clusters
"""
import os
import sys
from retry import retry

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # tests/
sys.path.append(THIS_DIR)

import rds_utilities, rds_config
from exceptions import InvalidInputError, InvalidDataOrConfigurationError


def set_log_types_db_cluster(rds_client, db_cluster_identifier, logger, apply_immediately):
    """
    function to set log_types depending on DB Engine
    @param rds_client:
    @param db_cluster_identifier:
    @param logger:
    @param apply_immediately:
    @return:
    """
    logger.info('Entering set_log_types_db_cluster()')

    dbs_clusters = rds_client.describe_db_clusters(DBClusterIdentifier=db_cluster_identifier)
    db_cluster = dbs_clusters["DBClusters"][0]

    db_engine = db_cluster["Engine"]
    db_engine_version = db_cluster["EngineVersion"]
    db_cluster_identifier = db_cluster["DBClusterIdentifier"]
    db_engine_mode = db_cluster["EngineMode"]
    major, minor = map(str, db_engine_version.split('.')[0:2])

    if not (db_engine and db_engine_version and db_cluster_identifier and db_engine_mode and major and minor):
        raise InvalidInputError("Empty string: 'db_engine' or 'db_engine_version' or 'db_cluster_identifier' or "
                                "'db_engine_mode' or 'major or minor' or all")

    logger.info(
        f'Engine={db_engine}, Major={major}, Minor={minor} Instance={db_cluster_identifier}, Mode={db_engine_mode}')

    # Provisioned has 'Log Exports'=audit. Serverless has None
    # MySQL v5.x (8.0 not released)
    if "mysql" in db_engine:
        # v5.7 has audit log types
        enable_log_types = ["audit"] if db_engine_mode == "provisioned" else [""]
        logger.info(f'LogType={enable_log_types}, "mysql" in db_engine AND db_engine_version.startswith("5.")')
    #
    # Postgres 9.6, 10, 11, 12
    elif "postgres" in db_engine:
        enable_log_types = ["postgresql"] if db_engine_mode == "provisioned" else [""]
        logger.info(f'LogType={enable_log_types}, "postgres" in db_engine')
    else:
        logger.error('Error: in enable_aurora_handler > logTypes_db_cluster: unsupported engine type')
        raise InvalidDataOrConfigurationError('enable_aurora_handler > logTypes_db_cluster: unsupported engine type')
    #
    # if DB Cluster has members, create/update Cluster and Parameter group
    # else (Serverless/Provisioned), create/update Cluster Parameter group
    # LogTypes exists for Cluster but not for Cluster members
    # LogTypes does not exist for Serverless Clusters
    #
    if db_cluster["DBClusterMembers"]:
        logger.info('DBClusterMembers in db_cluster')

        # apply changes to cluster
        cluster_parameter_group_changes(logger, rds_client, db_cluster, db_engine, major, minor,
                                        db_cluster_identifier, enable_log_types)
        # apply changes to instance
        for db_cluster_member in db_cluster["DBClusterMembers"]:
            db_instance_identifier = db_cluster_member["DBInstanceIdentifier"]
            db_cluster_instance = \
                rds_client.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)["DBInstances"][0]
            logger.info(
                f'db_instance_identifier = {db_instance_identifier}, db_cluster_instance = {db_cluster_instance}')
            rds_utilities.instance_parameter_group_changes(logger, rds_client, db_cluster_instance, db_engine,
                                                           major, minor, db_instance_identifier, is_cluster=True,
                                                           apply_immediately=apply_immediately)
    else:
        logger.info('No db_cluster_members in db_cluster')
        cluster_parameter_group_changes(logger, rds_client, db_cluster, db_engine, major, minor, db_cluster_identifier)
    logger.info('Exiting set_log_types_db_cluster')


# Start Cluster Parameter Group changes
def cluster_parameter_group_changes(logger, rds_client, db_cluster, db_engine, major, minor, db_instance_identifier,
                                    enable_log_types=None):
    """
    function to initiate changes to cluster_parameter_groups
    @param logger:
    @param rds_client:
    @param db_cluster:
    @param db_engine:
    @param major:
    @param minor:
    @param db_instance_identifier:
    @param enable_log_types:
    @return:
    """
    logger.info('Entering cluster_parameter_group_changes')

    val = rds_client.describe_db_cluster_parameter_groups()
    cluster_parameter_group_names = [
        cluster_parameter_group["DBClusterParameterGroupName"]
        for cluster_parameter_group in val["DBClusterParameterGroups"]
    ]

    logger.info('In db_cluster["DBClusterParameterGroup"]')
    db_cluster_parameter_group_name = db_cluster["DBClusterParameterGroup"]
    # create cluster parameter group name
    db_cluster_name = db_cluster["DBClusterIdentifier"]
    new_cluster_parameter_group_name = (
            rds_utilities.valid_file_name_creator(db_cluster_name)
            + "-" + db_engine + "-" + major + "-" + minor
    )

    ###
    # If db_cluster_parameter_group_name == default., new_cluster_parameter_group_name does not exist, create+update
    # new Parameter group
    # If db_cluster_parameter_group_name == default., new_cluster_parameter_group_name exists, update Parameter group
    # If db_cluster_parameter_group_name != default., update existing Parameter group with audit parameters
    ###
    if db_cluster_parameter_group_name.startswith("default."):
        logger.info('In db_cluster_parameter_group_name.startswith("default.")')
        if new_cluster_parameter_group_name not in cluster_parameter_group_names:
            # create new_cluster_parameter_group_name and assign params
            modify_cluster_parameter_groups(logger, rds_client, "create", db_engine, major, minor,
                                            new_cluster_parameter_group_name, db_cluster_parameter_group_name)
        # update new_cluster_parameter_group_name and assign params
        modify_cluster_parameter_groups(logger, rds_client, "update", db_engine, major, minor,
                                        new_cluster_parameter_group_name)
        db_parameter_group_name = new_cluster_parameter_group_name
    else:
        logger.info('db_cluster_parameter_group_name does not startswith("default.")')
        # update existing db_cluster_parameter_group_name and assign params
        modify_cluster_parameter_groups(logger, rds_client, "update", db_engine, major, minor,
                                        db_cluster_parameter_group_name)
        db_parameter_group_name = db_cluster_parameter_group_name

    create_modify_database_parameter_groups(logger, db_instance_identifier, db_parameter_group_name, enable_log_types,
                                            rds_client)

    logger.info('Exiting cluster_parameter_group_changes')


@retry(tries=15, delay=2, backoff=1.5)
def create_modify_database_parameter_groups(logger, db_instance_identifier, db_parameter_group_name, enable_log_types,
                                            rds_client):
    """
    Function to create or update database_parameter_groups
    Retry settings provides a duration sufficient for database to be available before raising an exception
    @param logger:
    @param db_instance_identifier:
    @param db_parameter_group_name:
    @param enable_log_types:
    @param rds_client:
    @return:
    """
    logger.info('Entering create_modify_database_parameter_groups')
    # assign newOptionGroupName to DB
    if enable_log_types is not None:
        logger.info(f'Modifying DB_Cluster with DBClusterIdentifier={db_instance_identifier}, \
                db_cluster_parameter_group_name={db_parameter_group_name}, EnableLogTypes={enable_log_types}')
        rds_client.modify_db_cluster(
            DBClusterIdentifier=db_instance_identifier,
            DBClusterParameterGroupName=db_parameter_group_name,
            CloudwatchLogsExportConfiguration={
                "EnableLogTypes": enable_log_types
            },
        )
    else:
        logger.info(f'Modifying DB_Cluster with DBClusterIdentifier={db_instance_identifier}, \
                db_cluster_parameter_group_name={db_parameter_group_name}')
        rds_client.modify_db_cluster(
            DBClusterIdentifier=db_instance_identifier,
            DBClusterParameterGroupName=db_parameter_group_name,
        )
    logger.info('Exiting create_modify_database_parameter_groups')


def get_cluster_parameter_group_family(logger, cluster_parameter_group_name, db_engine,
                                       default_cluster_parameter_group_name, major, minor, rds_client, task):
    """
    Function to return cluster parameter group family
    @param logger:
    @param cluster_parameter_group_name:
    @param db_engine:
    @param default_cluster_parameter_group_name:
    @param major:
    @param minor:
    @param rds_client:
    @param task:
    @return:
    """
    logger.info('Entering get_cluster_parameter_group_family')
    if db_engine in rds_config.POSTGRESQL_FAMILY:
        # During 'create' use default_cluster_parameter_group, else use existing or newly created
        if default_cluster_parameter_group_name and task == 'create':
            param_group_response = rds_client.describe_db_cluster_parameter_groups(
                DBClusterParameterGroupName=default_cluster_parameter_group_name)
        else:
            param_group_response = rds_client.describe_db_cluster_parameter_groups(
                DBClusterParameterGroupName=cluster_parameter_group_name)
        if not param_group_response.get('DBClusterParameterGroups'):
            cluster_parameter_group_family = db_engine + major
        else:
            cluster_parameter_group_family = param_group_response['DBClusterParameterGroups'][0][
                "DBParameterGroupFamily"]
    else:
        cluster_parameter_group_family = db_engine + major + '.' + minor[0]
    logger.info(f'cluster_parameter_group_family = {cluster_parameter_group_family}')
    return cluster_parameter_group_family


def modify_cluster_parameter_groups(logger, rds_client, task, db_engine, major, minor, cluster_parameter_group_name,
                                    default_cluster_parameter_group_name=None):
    """
    Function to set parameters based on engine type
    @param logger:
    @param rds_client:
    @param task:
    @param db_engine:
    @param major:
    @param minor:
    @param cluster_parameter_group_name:
    @param default_cluster_parameter_group_name:
    @return:
    """
    logger.info('Entering modify_cluster_parameter_groups')
    description = "For %s %s.%s audit logging" % (db_engine, major, minor)

    # Get cluster param group family
    cluster_parameter_group_family = get_cluster_parameter_group_family(logger, cluster_parameter_group_name, db_engine,
                                                                        default_cluster_parameter_group_name, major,
                                                                        minor, rds_client, task)
    #
    # Engine= MySQL
    #
    if db_engine in rds_config.MYSQL_FAMILY:
        logger.info('In db_engine==mysql')
        parameters = rds_config.AUDIT_LOG_PARAMS['MYSQL_CLUSTER_FAMILY']
    #
    # Engine= Postgres
    #
    elif db_engine in rds_config.POSTGRESQL_FAMILY:
        logger.info('In db_engine==postgres')
        parameters = rds_config.AUDIT_LOG_PARAMS['POSTGRESQL_CLUSTER_FAMILY']
    else:
        logger.error('Error: modify_cluster_parameter_groups: unsupported engine type')
        raise InvalidDataOrConfigurationError('modify_cluster_parameter_groups: unsupported engine type')

    create_modify_cluster_parameter_groups(logger, cluster_parameter_group_family, cluster_parameter_group_name,
                                           description, parameters, rds_client, task)
    logger.info('Exiting modify_cluster_parameter_groups')


@retry(tries=15, delay=2, backoff=1.5)
def create_modify_cluster_parameter_groups(logger, cluster_parameter_group_family, cluster_parameter_group_name,
                                           description, parameters, rds_client, task):
    """
    Function to create or update changes to cluster parameter groups
    Retry settings provides a duration sufficient for database to be available before raising an exception
    @param logger:
    @param cluster_parameter_group_family:
    @param cluster_parameter_group_name:
    @param description:
    @param parameters:
    @param rds_client:
    @param task:
    @return:
    """
    logger.info('Entering create_modify_cluster_parameter_groups()')
    if task == "create":
        logger.info('In task == "create"')
        # Create RDS Cluster Parameter Group
        rds_client.create_db_cluster_parameter_group(
            DBClusterParameterGroupName=cluster_parameter_group_name,
            DBParameterGroupFamily=cluster_parameter_group_family,
            Description=description,
        )
    if task in ["create", "update"]:
        logger.info('In task == "create" or task == "update"')
        # Add options to RDS Cluster Parameter Group
        rds_client.modify_db_cluster_parameter_group(
            DBClusterParameterGroupName=cluster_parameter_group_name, Parameters=parameters
        )
    logger.info('Exiting create_modify_cluster_parameter_groups()')


def failure_message(err):
    return {'status': 'failed', 'message': str(err)}
