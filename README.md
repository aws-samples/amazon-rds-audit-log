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
2. Clone the source code located at https://github.com/aws-samples/amazon-rds-audit-log
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

<img width="924" alt="image" src="https://github.com/aws-samples/amazon-rds-audit-log/assets/31387408/a7ec063e-c56a-4f97-ba7c-df5b11493b1f">

## Contributors
* Suresh Poopandi
* Abhay Kumar
* Mansoor Khan
