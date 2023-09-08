@integration_test
@rds-audit-log-api-implementation

Feature: Audit log enablement of RDS databases with status validation using the RDS Audit Log API

    Scenario Outline: Positive Scenario - 'Success' Audit Enablement and validation of RDS database instance when invoking RDS Audit Log API
        Given an authorized user makes the API call
        And an account exists
        And instance exists with details <database_identifier>, <engine>, <version>, <port>, <user>, <mode>
        When we invoke RDS Audit Log API lambda function
        Then API response contains a status code of 200
        And response contains the enablement success message
        And response contains the Step Function execution ARN which does the validation
        And the Step Function instance is running
        And the Step Function executes successfully to validate the audit setup

        Examples:
            | database_identifier   | engine        |  port  |  user       |  version  |    mode     |
            | mysql5-9069           | mysql         |  3306  |  admin      |  5.7.39   |    None     |
#            | mysql8-25-9069        | mysql         |  3306  |  admin      |  8.0.28   |    None     |
#            | postgres14-19073      | postgres      |  5432  |  postgres   |  14.4     |    None     |
#
#
#    Scenario Outline: Positive Scenario - 'Success' Audit enablement and validation of RDS cluster when invoking RDS Audit Log API.
#        Given an authorized user makes the API call
#        And an account exists
#        And cluster exists with details <cluster_identifier>, <engine>, <version>, <port>, <user>, <mode>
#        When we invoke RDS Audit Log API lambda function
#        Then API response contains a status code of 200
#        And response contains the enablement success message
#        And response contains the Step Function execution ARN which does the validation
#        And the Step Function instance is running
#        And the Step Function executes successfully to validate the audit setup
#
#        Examples:
#            | cluster_identifier        | engine             |  port  |  user       |  version   |    mode     |
#            | aurora-svls-mysql57-9069  | aurora-mysql       |  3306  |  admin      |  5.7.mysql_aurora.2.07.1    | serverless  |
#            | aurora-prov-mysql57-9069  | aurora-mysql       |  3306  |  admin      |  5.7.mysql_aurora.2.07.10  | provisioned |
#            | aurora-prov-pg12-9069     | aurora-postgresql  |  5432  |  postgres   |  12.9      | provisioned |
