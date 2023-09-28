"""
Unit tests for Ingress Lambda
"""
# pylint: disable=no-self-use, too-many-statements, too-many-locals, no-member, wrong-import-order, import-error, wrong-import-position, global-variable-undefined, unused-argument, missing-module-docstring, wildcard-import, bad-option-value, line-too-long, missing-final-newline, trailing-whitespace, disable=broad-except, simplifiable-if-expression, f-string-without-interpolation,function-redefined, undefined-variable, missing-function-docstring, logging-fstring-interpolation, logging-string-interpolation, unused-wildcard-import, unused-variable, logging-not-lazy, unused-import

import pytest
import os
import sys
import unittest
import json
from unittest import mock
from unittest.mock import Mock, patch
import logging
from botocore.exceptions import ClientError
from nose.tools import assert_equal, assert_true, assert_equals, assert_false

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # tests/
APP_DIR = os.path.normpath(os.path.join(THIS_DIR, '../app'))  # app/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../util'))  # util/
sys.path.append(APP_DIR)
sys.path.append(UTIL_DIR)

from exceptions import InvalidInputError, InvalidDataOrConfigurationError

class DBClusterNotFoundFault(BaseException):
    pass


MOCK_ENV_VARS = {
    "azure_auth_secret_name": "mock",
    "azure_auth_client_id": "mock",
    "ldap_group_name": "mock",
    "msft_tenant_id": "mock",
    "msft_app_id": "mock",
    "msft_client_roles": "mock",
    "user_keys_bucket": "mock",
    "account_secret_bucket": "mock",
    "aws_session_token": "mock",
    "aws_secret_access_key": "mock",
    "aws_key_id": "mock"
}


@pytest.fixture(autouse=True)
def mock_settings_env_vars():
    with mock.patch.dict(os.environ, MOCK_ENV_VARS):
        yield

with open('config.json') as env_config_file:
    config = json.load(env_config_file)

class TestAuditLogAPI(unittest.TestCase):

    @pytest.fixture(autouse=True)
    def mock_secret(self):
        with mock.patch('auth_utilities.get_secret') as mock_secret:
            mock_secret.return_value = '{"client_secret":"mock"}'
            yield mock_secret

    def setUp(self):
        """
        Initializer function
        @return:
        """
        # OS Env Variables used
        self.account_number = "1244343"


        self.evt_no_header = {}
        self.db_identifier = config['behave']['db_name']
        self.token = config['behave']['invalid_token']
        self.evt_bad_id = {'headers': {'authorization': self.token}, 'body': json.dumps(
            dict(account_id='abc', region=config['main']['region'], instance_or_cluster='instance',
                 db_identifier=self.db_identifier))}
        self.evt_no_body = {'headers': {'authorization': self.token}, 'body': {}}
        self.evt_with_token = {'headers': {'authorization': self.token}, 'body': json.dumps(
            dict(account_id=self.account_id, region=config['main']['region'], instance_or_cluster='instance',
                 db_identifier=self.db_identifier))}
        self.evt_bad_db_id = {'headers': {'authorization': self.token}, 'body': json.dumps(
            dict(account_id=self.account_id, region=config['main']['region'], instance_or_cluster='instance',
                 db_identifier=self.db_identifier))}
        self.evt_bad_cluster_id = {'headers': {'authorization': self.token}, 'body': json.dumps(
            dict(account_id=self.account_id, region=config['main']['region'], instance_or_cluster='cluster',
                 db_identifier='bad-id'))}
        self.token2 = {'requestContext': {'elb': {
            'targetGroupArn': 'arn:aws:elasticloadbalancing:us-east-1:687174582794:targetgroup/eec0f2a660db55b5094716137d31f566/c30765f83777e5dd'}},
            'httpMethod': 'POST', 'path': '/v1/rdsauditlog', 'queryStringParameters': {},
            'headers': {'accept': '*/*', 'accept-encoding': 'gzip, deflate, br',
                        'authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6Im5PbzNaRHJPRFhFSzFqS1doWHNsSFJfS1hFZyIsImtpZCI6Im5PbzNaRHJPRFhFSzFqS1doWHNsSFJfS1hFZyJ9.eyJhdWQiOiJodHRwczovL2NseC1hd3NhcGktcmRzLWF1ZGl0LWxvZy1kZXYuam5qLmNvbSIsImlzcyI6Imh0dHBzOi8vc3RzLndpbmRvd3MubmV0LzNhYzk0YjMzLTkxMzUtNDgyMS05NTAyLWVhZmRhNjU5MmEzNS8iLCJpYXQiOjE2MjAzMTc2MDMsIm5iZiI6MTYyMDMxNzYwMywiZXhwIjoxNjIwMzIxNTAzLCJhaW8iOiJFMlpnWUNqYlpMKzk5TGErZWQ5blYrUEhsUmI5QUE9PSIsImFwcGlkIjoiNTI4NjdkNjQtNWI2NC00OGVjLTgxMjctMDg1NGQ1OGE3NWQwIiwiYXBwaWRhY3IiOiIxIiwiaWRwIjoiaHR0cHM6Ly9zdHMud2luZG93cy5uZXQvM2FjOTRiMzMtOTEzNS00ODIxLTk1MDItZWFmZGE2NTkyYTM1LyIsIm9pZCI6IjlmZjBiMDUwLWZlMGMtNGJhZS05NmFiLTczNTdmNDBmODMwYSIsInJoIjoiMC5BUVFBTTB2Sk9qV1JJVWlWQXVyOXBsa3FOV1I5aGxKa1cteElnU2NJVk5XS2RkQUVBQUEuIiwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInN1YiI6IjlmZjBiMDUwLWZlMGMtNGJhZS05NmFiLTczNTdmNDBmODMwYSIsInRpZCI6IjNhYzk0YjMzLTkxMzUtNDgyMS05NTAyLWVhZmRhNjU5MmEzNSIsInV0aSI6IjlMUHQyN1BMWVUyTlNHNVdEU293QVEiLCJ2ZXIiOiIxLjAifQ.FhAQ7JnckUmxqtNPjhEffwhMdwm4kSDfXeWNVaTaNWuwUZl2y0h_gKFvpZqT3lv1FoI5MlYAGBfe4laBAAl87R7k-vijiFa9m9Izy8Vjlp1i5x3uerrcbXIFgqXe2nO2SH8z7j27MvXeZFO67MAhMZdoflyvQxNCbUKW_NFyGUhLEFdmPD72pwj0_2srf_5tJ8mSu-ZKv1JEuQSts-9P1W0MF4KSxCQLi393MBIae2NE2gtF0HVjgV_MNyBPhDGl9WUqCpwkWPABw7XzSxbKYqQk_7D8Bb3E9-J5hoy8swGVojIoIbDxVUMAjYcpI9Ayp95CNVl-xQFDY_lsIJaBuw',
                        'connection': 'keep-alive', 'content-length': '136',
                        'content-type': 'application/json',
                        'host': 'internal-rdsauditlogenableralb-135393021.us-east-1.elb.amazonaws.com',
                        'postman-token': 'c5d0b1b7-2e26-4abd-b647-7560368e1ede',
                        'user-agent': 'PostmanRuntime/7.26.10',
                        'x-amzn-trace-id': 'Root=1-609418c2-014516d036d98eb50064946f',
                        'x-forwarded-for': '10.53.219.132', 'x-forwarded-port': '80',
                        'x-forwarded-proto': 'http'},
            'body': '{\r\n\t"account_id": "abc-0123",\r\n\t"region": "us-east-1",\r\n\t"instance_or_cluster": "cluster",\r\n    "db_identifier": "aurora-svls-mysql57"\r\n}',
            'isBase64Encoded': False}


    def test_error_no_body(self):
        """
        Simulate failure when invalid POST body format is detected
        @return:
        """
        from enable_audit_handler import handler
        expected_result = 'Failure in Audit Log enablement. Details: the JSON object must be str, bytes or bytearray, not dict'
        actual_result = (json.loads(handler(self.evt_no_body, '')['body']))['error']
        assert_equals(actual_result, expected_result)

    def test_error_undefined_step_fn_arn(self):
        """
        Simulate failure when an invalid Step Function ARN is used
        @return:
        """
        from enable_audit_handler import handler
        expected_result = "Failure in Audit Log enablement. Details: OS Env input None in 'sfn_audit_log_validation_arn'"
        actual_result = (json.loads(handler(self.evt_with_token, '')['body']))['error']
        assert_equals(actual_result, expected_result)

    @mock.patch('enable_audit_handler.db_created_less_than_1hr')
    @mock.patch('enable_audit_handler.boto3_client')
    @mock.patch.dict(os.environ, {"enable_sm_arn": "ARN"})
    def test_error_bad_account(self, mock_boto3, db_created_less_than_1hr):
        """
        Simulate failure when an invalid account is used
        @param db_created_less_than_1hr:
        @return:
        """
        from enable_audit_handler import handler
        db_created_less_than_1hr.return_value = True
        mock_boto3.side_effect = InvalidDataOrConfigurationError('Invalid account')
        expected_result = "Failure in Audit Log enablement. Details: Invalid account"
        actual_result = (json.loads(handler(self.evt_bad_id, '')['body']))['error']
        assert_equals(actual_result, expected_result)

    ##covered in bdd
    @mock.patch('enable_audit_handler.db_created_less_than_1hr')
    @mock.patch('enable_audit_handler.boto3_client')
    @mock.patch.dict(os.environ, {"enable_sm_arn": "ARN"})
    def test_error_bad_database_id(self, mock_boto3, db_created_less_than_1hr):
        """
        Simulate failure when db_identifier is invalid
        @param db_created_less_than_1hr:
        @return:
        """
        from enable_audit_handler import handler
        db_created_less_than_1hr.return_value = True
        error = {
            "Error": {
                "Code": "DBInstanceNotFound",
                "Message": "DBInstance TestDB not found.",
            }
        }
        mock_boto3.return_value.describe_db_instances.side_effect = ClientError(error, "DBInstanceNotFound")
        expected_result = 'Failure in Audit Log enablement. Details: DBInstance TestDB not found.'
        actual_result = (json.loads(handler(self.evt_bad_db_id, '')['body']))['error']
        assert_equals(actual_result, expected_result)

    ##covered in bdd
    @mock.patch('enable_audit_handler.db_created_less_than_1hr')
    @mock.patch('enable_audit_handler.boto3_client')
    @mock.patch.dict(os.environ, {"enable_sm_arn": "ARN"})
    def test_error_bad_cluster_id(self, mock_boto3,db_created_less_than_1hr):
        """
        Simulate failure when db_identifier is invalid
        @param db_created_less_than_1hr:
        @return:
        """
        from enable_audit_handler import handler
        db_created_less_than_1hr.return_value = True
        error = {
            "Error": {
                "Code": "DBClusterNotFoundFault",
                "Message": "DBCluster bad-id not found.",
            }
        }
        mock_boto3.return_value.describe_db_clusters.side_effect = ClientError(error, "DBClusterNotFoundFault")
        expected_result = 'Failure in Audit Log enablement. Details: DBCluster bad-id not found.'
        actual_result = (json.loads(handler(self.evt_bad_cluster_id, '')['body']))['error']
        assert_equals(actual_result, expected_result)

    # End to End tests
    @patch("enable_audit_handler.get_database_master_password")
    @patch("enable_audit_handler.db_created_less_than_1hr")
    @patch("enable_audit_handler.enable_instance_audit_log")
    @patch("enable_audit_handler.start_validation_step_function")
    @patch("enable_audit_handler.boto3_client")
    @mock.patch.dict(os.environ, {"enable_sm_arn": "ARN"})
    def test_success_instance_audit_enable(self, mock_boto3, mock_stepfn, mock_result, mock_db_create_check,
                                           mock_password):
        """
        Simulate success for an RDS event of type instance (not cluster)
        @type mock_password:
        @param mock_boto3:
        @param mock_stepfn:
        @param mock_result:
        @param mock_db_create_check:
        @return:
        """
        from enable_audit_handler import handler
        mock_db_create_check.return_value = True
        mock_result.return_value = {"status": "success", "message": "Audit logging has been successfully enabled"}
        mock_stepfn.return_value = {'executionArn': 'step_fn_arn'}
        mock_boto3.return_value.describe_db_instances.return_value = config['behave']['mock_mysql57']
        mock_password.return_value = config['behave']['db_master_password']
        expected_output = {"message": "Audit logging has been successfully enabled", "sfn_execution_arn": "step_fn_arn"}

        test_input = dict(instance_or_cluster='instance', db_identifier='', region='', account_id='')
        event = {'headers': {}, 'body': json.dumps(test_input)}
        response = handler(event, '')
        message = json.loads(response.get('body'))
        assert_equal(message, expected_output)

    @patch("enable_audit_handler.get_database_master_password")
    @patch("enable_audit_handler.db_created_less_than_1hr")
    @patch("enable_audit_handler.enable_aurora_audit_log")
    @patch("enable_audit_handler.start_validation_step_function")
    @patch("enable_audit_handler.boto3_client")
    @mock.patch.dict(os.environ, {"enable_sm_arn": "ARN"})
    def test_success_serverless_cluster(self, mock_boto3, mock_stepfn, mock_result, mock_db_create_check,
                                        mock_db_password):
        """
        Simulates success when event is of cluster type 'Serverless'
        @param mock_boto3:
        @param mock_stepfn:
        @param mock_result:
        @param mock_db_create_check:
        @param mock_db_password:
        @return:
        """
        from enable_audit_handler import handler
        mock_db_create_check.return_value = True
        mock_result.return_value = {"status": "success", "message": "Audit logging has been successfully enabled"}
        mock_stepfn.return_value = {'executionArn': 'step_fn_arn'}
        mock_boto3.return_value.describe_db_clusters.return_value = config['behave']['mock_cluster_svls_mysql57']
        mock_db_password.return_value = 'Test1234'
        expected_output = {"message": "Audit logging has been successfully enabled", "sfn_execution_arn": "step_fn_arn"}

        test_input = dict(instance_or_cluster='cluster', db_identifier='', region='', account_id='')
        event = {'headers': {}, 'body': json.dumps(test_input)}
        response = handler(event, '')
        message = json.loads(response.get('body'))
        assert_equal(message, expected_output)

    @patch("enable_audit_handler.db_created_less_than_1hr")
    @patch("enable_audit_handler.enable_aurora_audit_log")
    @patch("enable_audit_handler.start_validation_step_function")
    @patch("enable_audit_handler.boto3_client")
    @mock.patch.dict(os.environ, {"enable_sm_arn": "ARN"})
    def test_failure_provisioned_cluster(self, mock_boto3, mock_stepfn, mock_result, mock_db_create_check):
        """
        Simulates failure when incoming event is detected from a cluster of type 'Provisioned'.
        Only 'Serverless' cluster types are supported.
        Instances of type 'Provisioned' are supported which in turn audit enable their corresponding cluster
        @param mock_boto3:
        @param mock_stepfn:
        @param mock_result:
        @param mock_db_create_check:
        @return:
        """
        from enable_audit_handler import handler
        mock_db_create_check.return_value = True
        mock_result.return_value = {"status": "success", "message": "Audit logging has been successfully enabled"}
        mock_stepfn.return_value = {'executionArn': 'step_fn_arn'}
        mock_boto3.return_value.describe_db_clusters.return_value = config['behave']['mock_cluster_prov_mysql57']
        expected_output = 'Failure in Audit Log enablement. Details: Provisioned cluster event detected is not-supported'

        test_input = dict(instance_or_cluster='cluster', db_identifier='', region='', account_id='')
        event = {'headers': {}, 'body': json.dumps(test_input)}
        response = handler(event, '')
        message = (json.loads(response.get('body')))['error']
        assert_equal(message, expected_output)

    @patch("enable_audit_handler.get_database_master_password")
    @patch("enable_audit_handler.db_created_less_than_1hr")
    @patch("enable_audit_handler.enable_instance_audit_log")
    @patch("enable_audit_handler.start_validation_step_function")
    @patch("enable_audit_handler.boto3_client")
    @mock.patch.dict(os.environ, {"enable_sm_arn": "ARN"})
    def test_failure_lambda_audit_failed(self, mock_boto3, mock_stepfn, mock_result, mock_db_create_check,
                                         mock_db_password):
        """
        Simulates failure returned from RDS instance enablement
        @param mock_boto3:
        @param mock_stepfn:
        @param mock_result:
        @param mock_db_create_check:
        @param mock_db_password:
        @return:
        """
        from enable_audit_handler import handler
        mock_db_create_check.return_value = True
        # 200 below indicates no Lambda invoke issue
        mock_result.return_value = {"status": "failure", "message": "Audit logging failed"}
        mock_stepfn.return_value = {'executionArn': 'step_fn_arn'}
        mock_db_password.return_value = 'Test12345'
        mock_boto3.return_value.describe_db_instances.return_value = config['behave']['mock_mysql57']
        expected_output = "Failure in Audit Log enablement. Details: Incoming input has 'None' in 'account_id' or " \
                          "'region' or 'db_type' or 'db_identifier or all"

        test_input = dict(db_type='instance', db_identifier='', db_region='', db_account_id='')
        event = {'headers': {}, 'body': json.dumps(test_input)}
        response = handler(event, '')
        message = (json.loads(response.get('body')))['error']
        assert_equal(message, expected_output)

    @patch("enable_audit_handler.db_created_less_than_1hr")
    @patch("enable_audit_handler.enable_aurora_audit_log")
    @patch("enable_audit_handler.start_validation_step_function")
    @patch("enable_audit_handler.boto3_client")
    @mock.patch.dict(os.environ, {"enable_sm_arn": "ARN"})
    def test_failure_provisioned_cluster(self, mock_boto3, mock_stepfn, mock_result, mock_db_create_check):
        """
        Simulates failure when incoming event is detected from a cluster of type 'Provisioned'.
        Only 'Serverless' cluster types are supported.
        Instances of type 'Provisioned' are supported which in turn audit enable their corresponding cluster
        @param mock_boto3:
        @param mock_stepfn:
        @param mock_result:
        @param mock_db_create_check:
        @return:
        """
        from enable_audit_handler import handler
        mock_db_create_check.return_value = True
        mock_result.return_value = {"status": "success", "message": "Audit logging has been successfully enabled"}
        mock_stepfn.return_value = {'executionArn': 'step_fn_arn'}
        mock_boto3.return_value.describe_db_clusters.return_value = config['behave']['mock_cluster_prov_mysql57']
        expected_output = 'Failure in Audit Log enablement. Details: Provisioned cluster event detected is not-supported'

        test_input = dict(instance_or_cluster='cluster', db_identifier='', region='', account_id='')
        event = {'headers': {}, 'body': json.dumps(test_input)}
        response = handler(event, '')
        message = (json.loads(response.get('body')))['error']
        assert_equal(message, expected_output)


if __name__ == '__main__':
    unittest.main()
