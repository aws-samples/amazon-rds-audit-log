# Secure GxP compliance by automating the RDS security audit log export process

This repository guides users, to explore the significance of RDS security audit logs in GxP environments and
discuss how automating the log export process can enhance security while streamlining
compliance efforts.


## Prerequisites

This solution requires the Lambda function deployed on the governance account to run audit enablement SQL queries in the RDS database instances hosted on the workload account. The following configuration should be in place for the RDS Audit Log API to function correctly.  

1. Governance account's VPC hosting the audit enablement Lambda has connectivity to all workload accounts VPCs hosting RDS database instance via VPC peering or Transit Gateway. 
2. All RDS database instances should have a Security Group that allows inbound connections on appropriate ports from the Lambda functions hosted on the governance account. 


## Code

The code for this pattern is available on github, in the amazon-rds-audit-log repository. The code repository contains the following files and folders:
* alb directory - Contains alb.yml serverless template to create Application Load Balancer in Governance Account.
* lambda directory - Contain Code for AWS lambda and their serverless template. it contains BDD test scenario as well.
* stepfunctions directory - Contains serverless template to create step functions.
* Dockerfile - Docker steps 
* deployment_config.yml - Configuration settings, like VPC id, security groups
* serverless-iam-roles.yml - This will create IAM role in Governance Account.
* audit-log-automation-workload-accounts.yaml - Should be run in Worlkload Accounts and creates Eventbridge and IAM roles in the Accounts
  

## Deployment Instructions

To install the RDS Audit Log API in your designated governance account, execute the following steps:


1. Make sure to have both docker and serverless in your deployment environment.  These two components are required for deploying this solution. 
2. Clone the source code located at https://github.com/aws-samples/amazon-rds-audit-log.
3. Modify the deployment-config.yml in the root folder to have appropriate resource values for VPCs, Security Groups, Subnets, and S3 bucket names. 
4. Run the following command to install the API in your governance account.

    `serverless deploy`


## Testing

To validate the functionality of the RDS audit log solution, utilize the provided boto3 code snippet below. This code initiates the creation of an Amazon RDS MySQL server within a designated workload account. This action, in turn, serves as the catalyst that triggers the audit log workflow.
```
import boto3
conn = boto3.client('rds')

response = conn.create_db_instance(
        AllocatedStorage=10,
        DBName="test",
        DBInstanceIdentifier="mysql5-9069",
        DBInstanceClass="db.t3.medium",
        Engine="mysql",
        MasterUsername="root",
        Port=3306,
        VpcSecurityGroupIds=["***"],
        ManageMasterUserPassword=True
    )
```
## How it works

<img width="924" alt="image" src="https://github.com/aws-samples/amazon-rds-audit-log/blob/new_main/images/rdd-audit-log.png">

The workflow steps are as follows:

1. An Amazon <a href="https://aws.amazon.com/eventbridge/">EventBridge</a> rule, in the workload account, triggers the custom Audit Log API, developed as part of this solution, whenever an RDS instance is created.
2. The API starts a Step Functions workflow that enables the database audit log and waits for successful enablement.
3. The Enable Audit Log Lambda function describes the provisioned database instance and read the secret managed by RDS in <a href="https://aws.amazon.com/secrets-manager/">AWS Secrets Manager</a> for the master user password and connect with the database instance. The Enable Audit Lambda functions also reads the <a href="https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithParamGroups.html">parameter groups</a> and <a href="https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithOptionGroups.html">option groups</a> associated with the DB instance and updates the parameter for enabling the audit log.
4. Database engines log user activities into an <a href="https://aws.amazon.com/cloudwatch/">Amazon CloudWatch log</a> as a database audit log.
5. When the database engine writes the first entry into the CloudWatch log stream, that results in the creation of a new log stream. This CloudWatch log stream creation event triggers a Lambda function.
6. The function creates a new Firehose delivery stream to stream logs from CloudWatch to <a href="https://aws.amazon.com/s3/">Amazon S3</a>.
7. <a href="https://aws.amazon.com/kinesis/data-firehose/">Amazon Kinesis Data Firehose</a> reads the audit log from the CloudWatch log stream and writes the data to Amazon Simple Storage Service (Amazon S3).
8. Amazon RDS for SQL Server can upload the audit logs to Amazon Simple Storage Service (Amazon S3) by using built-in <a href="https://docs.aws.amazon.com/prescriptive-guidance/latest/sql-server-auditing-on-aws/auditing-rds-sql-instances.html">SQL Server audit mechanisms</a>.
9. By default, CloudWatch logs are kept indefinitely and never expire. You can adjust the retention policy for the log group by choosing a retention period between 10 years and one day. In order to reduce cost, this solution configures the CloudWatch logs retention period to 1 day. For optimizing the cost for logs stored on S3, you can configure <a href="https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html">Amazon S3 Lifecycle policies</a> or leverage the <a href="https://aws.amazon.com/s3/storage-classes/intelligent-tiering/">S3 Intelligent-Tiering storage class</a>.

## Contributors
* Suresh Poopandi
* Abhay Kumar
* Mansoor Khan
