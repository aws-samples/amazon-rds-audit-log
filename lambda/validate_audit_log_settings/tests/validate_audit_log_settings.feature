@integration_test
@rds-audit-log-api-implementation

Feature: Validate audit log settings in RDS instances and clusters
    # RDS Instance
    Scenario: Positive Scenario - Successful audit log validation of an RDS MySQL instance with 'Option Group'
        Given an RDS MySQL database exists
        When RDS Audit Log API is invoked
        And the database instance is audit log enabled
        Then validation Step Function execution begins
        And Step Function is running and invokes validation Lambda
        And Step Function concludes with status success and validation passed message

#    Scenario: Positive Scenario - Successful audit log validation of an RDS instance with 'Parameter Group'
#        Given an RDS PostgreSQL database exists
#        When RDS Audit Log API is invoked
#        And the database instance is audit log enabled
#        Then validation Step Function execution begins
#        And Step Function is running and invokes validation Lambda
#        And Step Function concludes with status success and validation passed message

    # RDS Instance: MS-SQLServer
#    Scenario: Positive Scenario - Successful audit log validation of RDS MS SQLServer with 'Option Group'
#        Given an RDS SQLServer database exists
#        When RDS Audit Log API is invoked
#        And the database instance is audit log enabled
#        Then validation Step Function execution begins
#        And Step Function is running and invokes validation Lambda
#        And Step Function concludes with status success and validation passed message

#    # Aurora Serverless
#    Scenario: Positive Scenario - Successful audit log validation of Aurora Serverless with 'Cluster Parameter Group'
#        Given an RDS Aurora Serverless database exists
#        When RDS Audit Log API is invoked
#        And the database instance is audit log enabled
#        Then validation Step Function execution begins
#        And Step Function is running and invokes validation Lambda
#        And Step Function concludes with status success and validation passed message

#    # Aurora Provisioned
#    Scenario: Positive Scenario - Successful audit log validation of an Aurora Provisioned database
#        Given an RDS Aurora Provisioned database exists
#        When RDS Audit Log API is invoked
#        And the database instance is audit log enabled
#        Then validation Step Function execution begins
#        And Step Function is running and invokes validation Lambda
#        And Step Function concludes with status success and validation passed message

#    Scenario: Negative Scenario - Failed validation of an Aurora Provisioned database with invalid 'Cluster Parameter Group'
#        Given an RDS Aurora Provisioned database exists
#        When RDS Audit Log API is invoked
#        And the database instance is_not audit log enabled
#        Then validation Step Function execution begins
#        And Step Function is running and invokes validation Lambda
#        And Step Function concludes with status failed and validation failed message
#
#    Scenario: Negative Scenario - Failed validation of an Aurora Provisioned database with invalid 'Instance Parameter Group'
#        Given an RDS Aurora Provisioned database exists
#        When RDS Audit Log API is invoked
#        And the instance parameter group is not audit log enabled
#        Then validation Step Function execution begins
#        And Step Function is running and invokes validation Lambda
#        And Step Function concludes with status failed and validation failed message
#
#    Scenario: Negative Scenario - Failed validation of an Aurora Provisioned database with invalid 'Cluster and Instance Parameter Group'
#        Given an RDS Aurora Provisioned database exists
#        When RDS Audit Log API is invoked
#        And the database instance is_not audit log enabled
#        And the instance parameter group is not audit log enabled
#        Then validation Step Function execution begins
#        And Step Function is running and invokes validation Lambda
#        And Step Function concludes with status failed and validation failed message