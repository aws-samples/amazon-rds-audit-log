"""
Ingress Lambda. Entry point to the RDS Audit Log Enable API
"""
import os
import sys
import json
import boto3
from datetime import datetime, timedelta

from botocore.exceptions import ClientError

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # app/
API_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../'))  # lambda/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../util'))  # util/
sys.path.append(THIS_DIR)
sys.path.append(API_DIR)
sys.path.append(UTIL_DIR)

from client_utilities import ClientUtilities
from auth_utilities import auth, Logger
from rds_utilities import set_log_types_db_instance
from aurora_utilities import set_log_types_db_cluster
from exceptions import InvalidInputError, InvalidDataOrConfigurationError, FailedAuditLogEnableError


def handler(event, context):
    """
    Invoke audit api after authorizing request
    Args:
        event: AWS lambda input event
        context: AWS lambda context
    Returns:
        status_code
    """
    global logger
    logger = Logger()
    logger.set_new_uuid()

    if event.get('httpMethod') == 'OPTIONS':
        return {
            "isBase64Encoded": False,
            "statusCode": 200,
            "statusDescription": "200 OK",
            "headers": get_response_headers(),
            "body": ""
        }

    logger.info(f'Event={event}')
    logger.info(f'context={context}')

    output = entry_point_with_auth(event)
    logger.info(f'Output={output}')
    return output


def entry_point_with_auth(event):
    """
    Invoke audit api after authorizing request
    Args:
        event: AWS lambda input event
    Returns:
        status_code
    """
    logger.info('Entering entry_point_with_auth()')
    error_message = 'Failure in Audit Log enablement. Details'
    try:
        if auth(event):
            logger.info("Authorization success")
    except Exception as err:
        logger.error(f'{error_message}: {err}')
        logger.error('Authorization failed: User not-authorized')
        if "Authorization header not found" in str(err):
            logger.error('Authorization header not found')
            return send_response(status_code=500, message={"error": f'{error_message}: Authorization failed'})
        return send_response(status_code=404, message={"error": f'{error_message}: Authorization failed'})

    try:
        output = entry_point(event)
        return send_response(status_code=200, message=output)
    except InvalidInputError as err:
        logger.error(f'{error_message}: {err}')
        return send_response(status_code=400, message={"error": f'{error_message}: {err}'})
    except InvalidDataOrConfigurationError as err:
        logger.error(f'{error_message}: {err}')
        return send_response(status_code=404, message={"error": f'{error_message}: {err}'})
    except Exception as err:
        logger.error(f'{error_message}: {err}')
        return send_response(status_code=500, message={"error": f'{error_message}: {err}'})


# noinspection PyTypeChecker
def entry_point(event):
    """
    enabler audit database logging on target account
    Args:
        event: AWS lambda input event
    Returns:
        status_code
    """
    logger.info('Entering entry_point()')

    # Extract body for POST request
    body = json.loads(event.get('body'))

    account_id = body.get('account_id', None)
    region = body.get('region', None)
    db_type = body.get('instance_or_cluster', None)
    db_identifier = body.get('db_identifier', None)

    if None in (account_id, region, db_type, db_identifier):
        raise InvalidInputError("Incoming input has 'None' in 'account_id' or 'region' or 'db_type' or "
                                "'db_identifier or all")

    # Get Env vars
    sfn_audit_log_validation_arn = os.environ.get('enable_sm_arn', None)

    if sfn_audit_log_validation_arn is None:
        raise InvalidInputError("OS Env input None in 'sfn_audit_log_validation_arn'")

    # RDS and IAM resources will be created in the accounts
    target_client = ClientUtilities()
    rds_client = target_client.boto3_client(account_id, 'rds', region)  # Target account client
    iam_client = target_client.boto3_client(account_id, 'iam', region)
    lambda_client = boto3_client('lambda', region)
    sfn_client = boto3_client( 'stepfunctions', region)
    sm_client = target_client.boto3_client(account_id, 'secretsmanager', region)

    if db_type == 'cluster':
        logger.info('In db_type == "cluster"')

        try:
            dbs_clusters = rds_client.describe_db_clusters(DBClusterIdentifier=db_identifier)
        except ClientError as err:
            if err.response['Error']['Code'] == "DBClusterNotFoundFault":
                error_message = err.response['Error']['Message']
                raise InvalidDataOrConfigurationError(error_message)
            else:
                raise FailedAuditLogEnableError(f'Details: {err}')
        except Exception as err:
            raise FailedAuditLogEnableError(f'Details: {err}')

        db_cluster = dbs_clusters["DBClusters"][0]
        db_maint_window = db_cluster["PreferredMaintenanceWindow"]

        db_apply_immediate = db_created_less_than_1hr(db_cluster['ClusterCreateTime'])

        db_engine_mode = db_cluster["EngineMode"]

        # if cluster type = provisioned then ignore
        if "serverless" not in db_engine_mode:
            raise InvalidDataOrConfigurationError('Provisioned cluster event detected is not-supported')

        rsp_audit_status = enable_aurora_audit_log(db_apply_immediate, db_identifier, rds_client)

    # DB Instance: Aurora Provisioned Instance (cluster) and RDS Instance (non-cluster)
    elif db_type == 'instance':
        logger.info('In db_type == "instance"')

        # If DB Instance not valid then throw exception
        try:
            db_instances = rds_client.describe_db_instances(DBInstanceIdentifier=db_identifier)
        except ClientError as err:
            if err.response['Error']['Code'] == "DBInstanceNotFound":
                error_message = err.response['Error']['Message']
                raise InvalidDataOrConfigurationError(error_message)
            else:
                raise FailedAuditLogEnableError(f'Details: {err}')
        except Exception as err:
            raise FailedAuditLogEnableError(f'Details: {err}')

        db_instance = db_instances["DBInstances"][0]
        db_maint_window = db_instance["PreferredMaintenanceWindow"]

        db_engine = db_instance['Engine']
        db_engine = db_engine if not db_engine.startswith('aurora') else 'aurora'

        # db_apply_immediate = True if db create under 1hr (event) else False
        db_apply_immediate = db_created_less_than_1hr(db_instance['InstanceCreateTime'])

        # Aurora Provisioned: invoke Aurora Lambda using ClusterID i.e. db_identifier=ClusterID
        if db_engine == 'aurora' and 'DBClusterIdentifier' in db_instance:
            db_identifier = db_instance.get('DBClusterIdentifier')
            db_type = 'cluster'
            rsp_audit_status = enable_aurora_audit_log(db_apply_immediate, db_identifier, rds_client)
        else:
            # Get user and password for DB instance. Password is instance-<db_id>
            db_user = db_instance['MasterUsername']
            secret_data = db_instance['MasterUserSecret']
            db_credentials = get_database_master_password(sm_client, secret_data)
            rsp_audit_status = enable_instance_audit_log(db_apply_immediate, db_instance, db_identifier, db_credentials['password'],
                                                         db_user, rds_client, iam_client, account_id, region,
                                                         lambda_client)
    else:
        raise InvalidDataOrConfigurationError('Unknown incoming event. Not cluster or instance')

    logger.info(f"db_type={db_type}, db_identifier={db_identifier}, db_apply_immediate={db_apply_immediate}")

    if db_apply_immediate:
        # wait to allow DB to apply mods from above. If DB still locked then backoff/retry used to wait
        wait_till_seconds = 300
    else:
        # wait based on DB specific scheduled maintenance window
        wait_till_seconds = get_time_in_seconds_till_next_scheduled_window(db_maint_window)

    # If status=success start step fn validation else return err
    status = rsp_audit_status.get('status')
    message = rsp_audit_status.get('message')

    if status and message:
        # start validation step_fn if audit successful
        if 'success' in status:
            logger.info(f'region for validation state machine - {region}')
            response = start_validation_step_function(db_identifier, db_type, region,
                                                      sfn_audit_log_validation_arn,
                                                      sfn_client, wait_till_seconds, account_id, logger.get_uuid())
            if 'executionArn' in response:
                sfn_execution_arn = response.get('executionArn')
                logger.info(f'Step function started {sfn_execution_arn}')
                return {
                    "message": message,
                    "sfn_execution_arn": sfn_execution_arn
                }
            raise InvalidDataOrConfigurationError("'executionArn' not found in audit enablement response")
        raise InvalidDataOrConfigurationError('Success not returned during audit enablement')
    raise InvalidDataOrConfigurationError('Status and Message not detected')


def boto3_client(service, region):
    client = boto3.client(
        region_name=region,
        service_name=service,
    )
    return client


def enable_instance_audit_log(db_apply_immediate, db_instance, db_instance_identifier, db_password, db_user,
                              rds_client, iam_client, account_id, region, lambda_client=None):
    """
    Enables audit logging for RDS Instances
    @param db_apply_immediate:
    @param db_instance:
    @param db_instance_identifier:
    @param db_password:
    @param db_user:
    @param rds_client:
    @param iam_client:
    @param sm_client:
    @param account_id:
    @param region:
    @param lambda_client
    @return:
    """
    set_log_types_db_instance(
        rds_client,
        iam_client,
        account_id,
        region,
        db_instance,
        logger,
        db_user,
        db_password,
        db_apply_immediate,
        lambda_client
    )
    logger.info(f'Audit logging has been successfully enabled for DB={db_instance_identifier}')
    return {'status': 'success', 'message': 'Audit logging has been successfully enabled'}


def enable_aurora_audit_log(db_apply_immediate, db_cluster, rds_client):
    """
    Enable Audit logging for Aurora Clusters
    @param db_apply_immediate:
    @param db_cluster:
    @param rds_client:
    @return:
    """
    set_log_types_db_cluster(
        rds_client,
        db_cluster,
        logger,
        db_apply_immediate
    )
    logger.info(f'Audit logging has been successfully enabled for DB={db_cluster}')
    return {'status': 'success', 'message': 'Audit logging has been successfully enabled'}


def start_validation_step_function(db_identifier, db_type, region, sfn_audit_log_validation_arn, sfn_client,
                                   wait_till_seconds, account_id, logger_uuid):
    """
    Function triggers step function execution
    @param db_identifier:
    @param db_type:
    @param region:
    @param sfn_audit_log_validation_arn:
    @param sfn_client:
    @param wait_till_seconds:
    @param account_id:
    @param logger_uuid:
    @return:
    """
    try:
        return sfn_client.start_execution(
            stateMachineArn=sfn_audit_log_validation_arn,
            input=json.dumps({
                "db_type": db_type,  # cluster or instance
                "db_identifier": db_identifier,  # db_cluster_id or db_instance_id
                "wait_till_seconds": wait_till_seconds,  # 60s for immediate or custom for scheduled
                "db_region": region,
                "db_account_id": account_id,
                "logger_uuid": logger_uuid
            })
        )
    except sfn_client.exceptions.InvalidArn as err:
        raise InvalidDataOrConfigurationError(f"Validation error: InvalidArn. Details: {err}")
    except sfn_client.exceptions.InvalidExecutionInput as err:
        raise InvalidDataOrConfigurationError(f"Validation error: InvalidExecutionInput. Details: {err}")
    except sfn_client.exceptions.InvalidName as err:
        raise InvalidDataOrConfigurationError(f"Validation error: InvalidName. Details: {err}")
    except sfn_client.exceptions.StateMachineDoesNotExist as err:
        raise InvalidDataOrConfigurationError(f"Validation error: StateMachineDoesNotExist. Details: {err}")
    except sfn_client.exceptions.StateMachineDeleting as err:
        raise InvalidDataOrConfigurationError(f"Validation error: StateMachineDeleting. Details: {err}")
    except sfn_client.exceptions.ExecutionLimitExceeded as err:
        raise FailedAuditLogEnableError(f"Validation error: ExecutionLimitExceeded. Details: {err}")
    except Exception as err:
        raise FailedAuditLogEnableError(f"Failure in start_validation_step_function(). Details: {err}")


def db_created_less_than_1hr(db_created_time):
    """
    validates if DB was created <1h to determine applyImmediate
    @param db_created_time:
    @return: applyImmediate is True <1h or False >1h
    """
    try:
        db_created_time = db_created_time.replace(tzinfo=None)
        if datetime.now() - timedelta(hours=1) <= db_created_time <= datetime.now():
            # true if db create time is < 1h
            return True
        return False
    except Exception as err:
        raise FailedAuditLogEnableError(f"Error in db_created_less_than_1hr(). Details: {err}")


def get_time_in_seconds_till_next_scheduled_window(db_maint_window):
    """
    uses next_scheduled_window time to get time in seconds for step fn wait before start
    @param db_maint_window:
    @return: time in seconds
    """
    # db_maint_window format= 'ddd:hh24:mi-ddd:hh24:mi'
    # get end datetime + 1h to get seconds to start validation
    try:
        start_str, end_str = db_maint_window.split("-")
        end_day, end_hour, end_minute = end_str.split(":")

        days_mappings = {
            "mon": 1,
            "tue": 2,
            "wed": 3,
            "thu": 4,
            "fri": 5,
            "sat": 6,
            "sun": 7,
        }
        now = datetime.utcnow()

        day_int = days_mappings.get(end_day)
        add_days = 0

        if now.isoweekday() < day_int:
            add_days = day_int - now.isoweekday()
        elif now.isoweekday() > day_int:
            add_days = 7 + day_int - now.isoweekday()

        date = (now + timedelta(days=add_days)).replace(hour=int(end_hour), minute=int(end_minute), second=0,
                                                        microsecond=0)
        if date < now:
            date = date + timedelta(days=7)

        now = datetime.now()
        seconds = (date - now).total_seconds()
        # next_scheduled_window time + 1h to get to steady state
        seconds = round(seconds) + 3600
        return seconds
    except Exception as err:
        raise FailedAuditLogEnableError(f"Error in get_time_in_seconds_till_next_scheduled_window(). Details: {err}")


def send_response(status_code, message):
    """
    Send formatted HTTP response
    @param status_code:
    @param message:
    @return: send http response
    """
    return {
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": get_response_headers(),
        "body": json.dumps(message)
    }


def get_response_headers():
    """
    Return header for response message
    @return:
    """
    return {
        "Content-Type": "application/json",
        "Context-Id": logger.get_uuid(),
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, OPTIONS, HEAD",
        "Access-Control-Allow-Headers": "Content-Type, Access-Control-Allow-Headers, Authorization, X-Requested-With"
    }


def get_database_master_password(sm_client, secret_data):
    """
    Get master password of the RDS database
    @param sm_client:
    @param secret_data:
    @return:
    """
    response = sm_client.get_secret_value(
        SecretId=secret_data['SecretArn'],
    )
    return json.loads(response['SecretString'])
