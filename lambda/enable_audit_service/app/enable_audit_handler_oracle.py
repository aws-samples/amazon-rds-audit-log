import cx_Oracle
import os
import sys
import json
import jinja2

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # app/
API_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../'))  # lambda/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../util'))  # util/
sys.path.append(THIS_DIR)
sys.path.append(API_DIR)
sys.path.append(UTIL_DIR)
from auth_utilities import Logger


def handler(event, context):
    global logger
    logger = Logger()
    try:
        logger.set_uuid(event['uuid'])
        logger.info('In db_engine=oracle')
        host = event['host']
        db_name = event['db_name']
        #  Run SQL cmds
        oracle_server_run_sql_cmds(logger, host=host, user=event["db_user"],
                                   pwd=event["db_password"],
                                   db_name=db_name, db_engine_version=event["db_major_version"])
    except Exception as err:
        print(err)
        return {
            'statusCode': 500,
            'body': json.dumps("Error in executing Oracle SQL Commands - " + str(err))
        }
    return {
        'statusCode': 200,
        'body': json.dumps("successfully executed Oracle SQL Commands")
    }


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
    parent_dir = os.path.dirname(this_dir)  # Parent directory
    try:
        f = open(os.path.join(os.path.dirname(parent_dir), 'util', 'sql', engine_type, sql_file))
    except Exception as err:    # pylint: disable=broad-except
        print(f'render_sql() exception: {err}')
        return ''

    raw = f.read()
    t = jinja2.Template(raw)
    result = t.render(**kwargs)

    logger.info('Exiting render_sql()')

    return result


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
                raise Exception(str(err))

    except Exception as err:
        logger.error(f"connecting {host}:{port} exception: {err}")
        raise Exception(str(err))

    logger.info('Exiting oracle_server_run_sql_cmds()')
