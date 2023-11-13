"""
Test validation suite
"""
# pylint: disable=missing-class-docstring, wrong-import-position, import-error, no-self-use, missing-module-docstring, wildcard-import, bad-option-value, line-too-long, missing-final-newline, trailing-whitespace, disable=broad-except, simplifiable-if-expression, f-string-without-interpolation,function-redefined, undefined-variable, missing-function-docstring, logging-fstring-interpolation, logging-string-interpolation, unused-wildcard-import, unused-variable, logging-not-lazy, unused-import
import os
import sys
import unittest
import pytest
import json
from unittest import mock
from unittest.mock import patch

from nose.tools import assert_equal

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # tests/
APP_DIR = os.path.normpath(os.path.join(THIS_DIR, '../app'))  # app/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, '../../util'))  # util/
sys.path.append(APP_DIR)
sys.path.append(UTIL_DIR)

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

with open('../../../config/config.{}.json'.format(os.environ['ENV'])) as env_config_file:
    config = json.load(env_config_file)

class TestValidateAudit(unittest.TestCase):

    def setUp(self):
        self.region = config['main']['region']
        self.account = config['main']['account_id']
        self.mocked_error = 'mocked error'
        self.mock_uuid = 'abcd1234'

    # Parameter and Option Group Tests
    @patch("validate_audit_log_settings_handler.boto3_client")
    def test_success_on_parameter_groups_mocked(self, mock_boto3):
        from validate_audit_log_settings_handler import handler
        mock_boto3.return_value.describe_db_instances.return_value = config['behave']['mock_postgres14']

        with mock.patch('validate_audit_log_settings_handler.validate_instance_parameter_groups') as mock_val:
            test_input = dict(db_type='instance', db_identifier='', db_region='', db_account_id='')
            mock_val.return_value = {"status": "success", "message": "Validation passed"}
            response = handler(test_input, '')
            assert_equal(response['status'], 'success')
            assert_equal(response['message'], 'Validation passed')

    @patch("validate_audit_log_settings_handler.boto3_client")
    def test_failure_on_parameter_groups_mocked(self, mock_boto3):
        from validate_audit_log_settings_handler import handler
        mock_boto3.return_value.describe_db_instances.return_value = config['behave']['mock_postgres14']

        with mock.patch('validate_audit_log_settings_handler.validate_instance_parameter_groups') as mock_val:
            mock_val.return_value = {"status": "failed", "message": "Validation failed"}
            test_input = dict(db_type='instance', db_identifier='', db_region='', db_account_id='')
            response = handler(test_input, '')
            assert_equal(response['status'], 'failed')
            assert_equal(response['message'], 'Validation failed')

    @patch("validate_audit_log_settings_handler.boto3_client")
    def test_success_on_option_groups_mocked(self, mock_boto3):
        from validate_audit_log_settings_handler import handler
        mock_boto3.return_value.describe_db_instances.return_value = config['behave']['mock_mysql57']

        with mock.patch('validate_audit_log_settings_handler.validate_instance_option_groups') as mock_val:
            test_input = dict(db_type='instance', db_identifier='', db_region='', db_account_id='')
            mock_val.return_value = {"status": "success", "message": "Validation passed"}
            response = handler(test_input, '')
            assert_equal(response['status'], 'success')
            assert_equal(response['message'], 'Validation passed')

    @patch("validate_audit_log_settings_handler.boto3_client")
    def test_failure_on_option_groups_mocked(self, mock_boto3):
        from validate_audit_log_settings_handler import handler
        mock_boto3.return_value.describe_db_instances.return_value = config['behave']['mock_mysql57']

        with mock.patch('validate_audit_log_settings_handler.validate_instance_option_groups') as mock_val:
            mock_val.return_value = {"status": "failed", "message": "Validation failed"}
            test_input = dict(db_type='instance', db_identifier='', db_region='', db_account_id='')
            response = handler(test_input, '')
            assert_equal(response['status'], 'failed')
            assert_equal(response['message'], 'Validation failed')

    # mysql8
    @patch("validate_audit_log_settings_handler.boto3_client")
    def test_success_mysql8_v25_on_option_groups_mocked(self, mock_boto3):
        from validate_audit_log_settings_handler import handler
        mock_boto3.return_value.describe_db_instances.return_value = config['behave']['mock_mysql8_25']

        with mock.patch('validate_audit_log_settings_handler.validate_instance_option_groups') as mock_val:
            test_input = dict(db_type='instance', db_identifier='', db_region='', db_account_id='')
            mock_val.return_value = {"status": "success", "message": "Validation passed"}
            response = handler(test_input, '')
            assert_equal(response['status'], 'success')
            assert_equal(response['message'], 'Validation passed')

    @patch("validate_audit_log_settings_handler.boto3_client")
    def test_failure_mysql8_v20_on_option_groups_mocked(self, mock_boto3):
        from validate_audit_log_settings_handler import handler
        mock_boto3.return_value.describe_db_instances.return_value = config['behave']['mock_mysql8_23']

        with mock.patch('validate_audit_log_settings_handler.validate_instance_option_groups') as mock_val:
            test_input = dict(db_type='instance', db_identifier='', db_region='', db_account_id='')
            mock_val.return_value = {"status": "success", "message": "Validation passed"}
            response = handler(test_input, '')
            assert_equal(response['status'], 'failed')
            assert_equal(response['message'], 'Unsupported engine type detected. MySQL 8.0 version is < 8.0.25')


if __name__ == '__main__':
    unittest.main()
