# pylint: disable=logging-format-interpolation, redefined-outer-name, redefined-builtin, bad-option-value, import-error, missing-module-docstring
import os
import sys

import boto3
import logging

THIS_DIR = os.path.dirname(os.path.realpath(__file__))  # util/
UTIL_DIR = os.path.normpath(os.path.join(THIS_DIR, ''))  # util/
APP_DIR = os.path.normpath(os.path.join(THIS_DIR, '../enable_audit_service/app'))  # app/
sys.path.append(UTIL_DIR)
sys.path.append(APP_DIR)

lgr = logging.getLogger()
lgr.setLevel(logging.INFO)


class ClientUtilities:
    def __init__(self, logger=None):
        self.logger = logger
        if not self.logger:
            self.logger = lgr

    def boto3_client(self, account_id, service, region):
        """
        Return boto3 client for specified service
        @param account_id:
        @param service:
        @param region:
        @return:
        """
        rds_credentials = self.get_credentials_for_account(account_id)
        rds_client = boto3.client(
            region_name=region,
            service_name=service,
            aws_access_key_id=rds_credentials.get('AccessKeyId', ''),
            aws_secret_access_key=rds_credentials.get('SecretAccessKey', ''),
            aws_session_token=rds_credentials.get('SessionToken', '')
        )
        self.logger.info('Returning boto3 client')
        return rds_client

    def get_credentials_for_account(self, account_id) -> str:
        """
        Obtain credentials for specified account
        @param account_id:
        @return: credentials
        """
        sts_client = boto3.client('sts')

        # Call the assume_role method of the STSConnection object and pass the role
        # ARN and a role session name.
        assumed_role_object = sts_client.assume_role(
            RoleArn=f"arn:aws:iam::{account_id}:role/rds_audit_log_role",
            RoleSessionName="RDSAuditLogSession"
        )

        # From the response that contains the assumed role, get the temporary
        # credentials that can be used to make subsequent API calls
        return assumed_role_object['Credentials']
