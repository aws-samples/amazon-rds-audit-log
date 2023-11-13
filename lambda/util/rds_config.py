# The following items are for RDS.
ORACLE_FAMILY = 'oracle-ee'
MYSQL_FAMILY = ['mysql', 'aurora-mysql']
POSTGRESQL_FAMILY = ['postgres', 'aurora-postgresql']
MSSQL_FAMILY = ['sqlserver-ex', 'sqlserver-web', 'sqlserver-se', 'sqlserver-ee']

MSSQL_S3_BUCKET_ARN = ""
MSSQL_IAM_ROLE_ARN = ""
MSSQL_IAM_ROLE_NAME = "ms-admin-sqlserver-to-s3"

# Changes to dynamic parameters are applied immediately. Changes to static parameters require a reboot without
# fail-over to the DB cluster associated with the parameter group before the change can take effect.
# hence for static param only pending-reboot and immediate for all else
AUDIT_LOG_PARAMS = {
    'MYSQL_CLUSTER_FAMILY': [
        {
            "ParameterName": "server_audit_logging",
            "ParameterValue": "1",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "server_audit_logs_upload",
            "ParameterValue": "1",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "server_audit_events",
            "ParameterValue": "CONNECT,QUERY_DCL,QUERY_DDL",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "server_audit_excl_users",
            "ParameterValue": "",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "server_audit_incl_users",
            "ParameterValue": "",
            "ApplyMethod": "immediate",
        },
    ],
    'POSTGRESQL_CLUSTER_FAMILY': [
        {
            "ParameterName": "pgaudit.log",
            "ParameterValue": "ddl",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "pgaudit.role",
            "ParameterValue": "rds_pgaudit",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "shared_preload_libraries",
            "ParameterValue": "pgaudit",
            "ApplyMethod": "pending-reboot",
        },
        {
            "ParameterName": "ssl",
            "ParameterValue": "1",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "rds.force_ssl",
            "ParameterValue": "1",
            "ApplyMethod": "pending-reboot",
        },
        {
            "ParameterName": "log_statement",
            "ParameterValue": "ddl",
            "ApplyMethod": "pending-reboot",
        }
    ],
    'MYSQL_CLUSTER_INSTANCE_FAMILY': [
        {
            "ParameterName": "general_log",
            "ParameterValue": "1",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "slow_query_log",
            "ParameterValue": "1",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "log_output",
            "ParameterValue": "FILE",
            "ApplyMethod": "immediate",
        },
    ],
    'MYSQL_INSTANCE_FAMILY': [
        {
            "ParameterName": "general_log",
            "ParameterValue": "1",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "slow_query_log",
            "ParameterValue": "1",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "log_output",
            "ParameterValue": "FILE",
            "ApplyMethod": "immediate",
        },
    ],
    'POSTGRESQL_CLUSTER_INSTANCE_FAMILY': [
        {
            "ParameterName": "pgaudit.log",
            "ParameterValue": "all",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "pgaudit.role",
            "ParameterValue": "rds_pgaudit",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "shared_preload_libraries",
            "ParameterValue": "pgaudit",
            "ApplyMethod": "pending-reboot",
        },
    ],
    'POSTGRESQL_INSTANCE_FAMILY': [
        {
            "ParameterName": "pgaudit.log",
            "ParameterValue": "ddl",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "pgaudit.role",
            "ParameterValue": "rds_pgaudit",
            "ApplyMethod": "immediate",
        },
        {
            "ParameterName": "shared_preload_libraries",
            "ParameterValue": "pgaudit",
            "ApplyMethod": "pending-reboot",
        },
        {
            "ParameterName": "rds.force_ssl",
            "ParameterValue": "1",
            "ApplyMethod": "pending-reboot",
        },
        {
            "ParameterName": "log_statement",
            "ParameterValue": "ddl",
            "ApplyMethod": "pending-reboot",
        }
    ],
    'ORACLE_INSTANCE_FAMILY': [
        {
            "ParameterName": "audit_trail",
            "ParameterValue": "OS",
            "ApplyMethod": "pending-reboot",
        },
        {
            "ParameterName": "audit_sys_operations",
            "ParameterValue": "TRUE",
            "ApplyMethod": "pending-reboot",
        },
    ],
    'MYSQL_OPTIONS': [{
        "OptionName": "MARIADB_AUDIT_PLUGIN",
        "OptionSettings": [
            {"Name": "SERVER_AUDIT_EVENTS", "Value": "CONNECT,QUERY_DDL,QUERY_DML,QUERY_DCL"},
        ]
    }],
    'SQLSERVER_INSTANCE_FAMILY': [
        {
            "ParameterName": "rds.force_ssl",
            "ParameterValue": "1",
            "ApplyMethod": "pending-reboot",
        },
    ],
    'SQLSERVER_OPTIONS': [{
        "OptionName": "SQLSERVER_AUDIT",
        "OptionSettings": [
            {"Name": "S3_BUCKET_ARN", "Value": MSSQL_S3_BUCKET_ARN},
            {"Name": "IAM_ROLE_ARN", "Value": MSSQL_IAM_ROLE_ARN},
            {"Name": "ENABLE_COMPRESSION", "Value": "true"},
        ]
    }],
    'ORACLE_OPTIONS': [
        {
            "OptionName": "S3_INTEGRATION"
        },
        {
            "OptionName": "SQLT",
            "OptionSettings": [
                {
                    "Name": "LICENSE_PACK",
                    "Value": "T"
                },
            ]
        },
        {
            "OptionName": "NATIVE_NETWORK_ENCRYPTION",
            "OptionSettings": [
                {
                    "Name": "SQLNET.CRYPTO_CHECKSUM_SERVER",
                    "Value": "REQUIRED"
                },
                {
                    "Name": "SQLNET.CRYPTO_CHECKSUM_TYPES_SERVER",
                    "Value": "SHA256,SHA384,SHA512"
                },
                {
                    "Name": "SQLNET.ENCRYPTION_SERVER",
                    "Value": "REQUIRED"
                },
                {
                    "Name": "SQLNET.ENCRYPTION_TYPES_SERVER",
                    "Value": "AES256,AES128"
                },
                {
                    "Name": "SQLNET.ENCRYPTION_CLIENT",
                    "Value": "REQUIRED"
                },
                {
                    "Name": "SQLNET.ENCRYPTION_TYPES_CLIENT",
                    "Value": "AES256,AES128"
                },
                {
                    "Name": "SQLNET.CRYPTO_CHECKSUM_CLIENT",
                    "Value": "REQUIRED"
                },
                {
                    "Name": "SQLNET.CRYPTO_CHECKSUM_TYPES_CLIENT",
                    "Value": "SHA256,SHA384,SHA512"
                }
            ]
        }
    ]
}
