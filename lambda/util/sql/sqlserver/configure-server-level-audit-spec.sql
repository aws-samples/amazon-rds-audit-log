/*****************************CONFIGURE SERVER LEVEL AUDIT SPECIFICATION EVENT GROUPS***********************************/
USE [master]

IF EXISTS (SELECT * FROM sys.server_audit_specifications WHERE name = N'SERVER_MGMT_SPEC')
BEGIN
ALTER SERVER AUDIT SPECIFICATION [SERVER_MGMT_SPEC] WITH (STATE = OFF)
DROP SERVER AUDIT SPECIFICATION [SERVER_MGMT_SPEC]
END

CREATE SERVER AUDIT SPECIFICATION [SERVER_MGMT_SPEC]
	FOR SERVER AUDIT [SQL_NATIVE_AUDIT]
		ADD (SUCCESSFUL_LOGIN_GROUP),
		ADD (LOGOUT_GROUP),
		ADD (FAILED_LOGIN_GROUP),
		ADD (APPLICATION_ROLE_CHANGE_PASSWORD_GROUP),
		ADD (AUDIT_CHANGE_GROUP),
		ADD (DATABASE_CHANGE_GROUP),
		ADD (DATABASE_OBJECT_CHANGE_GROUP),
		ADD (DATABASE_OBJECT_OWNERSHIP_CHANGE_GROUP),
		ADD (DATABASE_OWNERSHIP_CHANGE_GROUP),
		ADD (DATABASE_PRINCIPAL_CHANGE_GROUP),
		ADD (DATABASE_PRINCIPAL_IMPERSONATION_GROUP),
		ADD (DATABASE_ROLE_MEMBER_CHANGE_GROUP),
		ADD (SCHEMA_OBJECT_OWNERSHIP_CHANGE_GROUP),
		ADD (SERVER_OBJECT_CHANGE_GROUP),
		ADD (SERVER_OPERATION_GROUP),
		ADD (SERVER_PRINCIPAL_CHANGE_GROUP),
		ADD (SERVER_PRINCIPAL_IMPERSONATION_GROUP),
		ADD (SERVER_ROLE_MEMBER_CHANGE_GROUP),
		ADD (DATABASE_OBJECT_PERMISSION_CHANGE_GROUP),
		ADD (DATABASE_PERMISSION_CHANGE_GROUP),
		ADD (SCHEMA_OBJECT_PERMISSION_CHANGE_GROUP),
		ADD (SERVER_OBJECT_PERMISSION_CHANGE_GROUP),
		ADD (SERVER_PERMISSION_CHANGE_GROUP)
	WITH (STATE = ON)