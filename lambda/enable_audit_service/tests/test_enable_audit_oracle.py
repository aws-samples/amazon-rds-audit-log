"""
Unit tests for Ingress Lambda
"""
# pylint: disable=no-self-use, too-many-statements, too-many-locals, no-member, wrong-import-order, import-error, wrong-import-position, global-variable-undefined, unused-argument, missing-module-docstring, wildcard-import, bad-option-value, line-too-long, missing-final-newline, trailing-whitespace, disable=broad-except, simplifiable-if-expression, f-string-without-interpolation,function-redefined, undefined-variable, missing-function-docstring, logging-fstring-interpolation, logging-string-interpolation, unused-wildcard-import, unused-variable, logging-not-lazy, unused-import

import os
import pytest
import sys
import unittest
import json
from unittest import mock
from unittest.mock import Mock, patch
from nose.tools import assert_equal, assert_true, assert_equals, assert_false

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # tests/
APP_DIR = os.path.normpath(os.path.join(THIS_DIR, '../app'))  # app/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../util'))  # util/
sys.path.append(APP_DIR)
sys.path.append(UTIL_DIR)

MOCK_ENV_VARS = {
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

    def setUp(self):
        """
        Initializer function
        @return:
        """
        # OS Env Variables used
        self.account_number = config['main']['account_number']
        self.account_id = config['main']['account_id']


        self.evt_no_header = {}
        self.db_identifier = config['behave']['db_name']
        self.token = config['behave']['invalid_token']
        self.evt_bad_id = {'headers': {'authorization': self.token}, 'body': json.dumps(
            dict(account_id='abc-0xx', region=config['main']['region'], instance_or_cluster='instance',
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

    @patch("enable_audit_handler.get_database_master_password")
    @patch("enable_audit_handler.db_created_less_than_1hr")
    @patch("enable_audit_handler.start_validation_step_function")
    @patch("enable_audit_handler.boto3_client")
    @mock.patch.dict(os.environ, {"enable_sm_arn": "ARN"})
    def test_success_instance_audit_enable(self, mock_boto3, mock_stepfn, mock_db_create_check,
                                           mock_password):
    # def test_success_instance_audit_enable(self, mock_boto3, mock_stepfn, mock_result, mock_db_create_check,
    #                                        mock_password):
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
        # mock_result.return_value = {"status": "success", "message": "Audit logging has been successfully enabled"}
        mock_stepfn.return_value = {'executionArn': 'step_fn_arn'}
        mock_boto3.return_value.describe_db_instances.return_value = config['behave']['mock_oracle_sql']
        mock_password.return_value = config['behave']['db_master_password']
        expected_output = {"message": "Audit logging has been successfully enabled", "sfn_execution_arn": "step_fn_arn"}

        test_input = dict(instance_or_cluster='instance', db_identifier='', region='', account_id='')
        event = {'headers': {}, 'body': json.dumps(test_input)}
        response = handler(event, '')
        message = json.loads(response.get('body'))
        # assert_equal(message, expected_output)


if __name__ == '__main__':
    unittest.main()