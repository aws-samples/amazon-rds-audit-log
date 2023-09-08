/*****************************CREATE JOB TO SEND EVENTS TO S3 AND ADD AUDIT TO NEW DBS**********************************/
USE [msdb]

IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = 'SQLNATIVEAUDIT_JOB')
EXEC msdb..sp_delete_job @job_name = 'SQLNATIVEAUDIT_JOB'

/****** Object:  Job [SQLNATIVEAUDIT_JOB]    Script Date: 9/23/2021 11:27:22 AM ******/
BEGIN TRANSACTION
DECLARE @ReturnCode INT
DECLARE @sys_usr CHAR(30)
SELECT @ReturnCode = 0
/****** Object:  JobCategory [[Uncategorized (Local)]]    Script Date: 9/23/2021 11:27:23 AM ******/
IF NOT EXISTS (SELECT name FROM msdb.dbo.syscategories WHERE name=N'[Uncategorized (Local)]' AND category_class=1)
BEGIN
EXEC @ReturnCode = msdb.dbo.sp_add_category @class=N'JOB', @type=N'LOCAL', @name=N'[Uncategorized (Local)]'
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback

END

DECLARE @jobId BINARY(16)
EXEC @ReturnCode =  msdb.dbo.sp_add_job @job_name=N'SQLNATIVEAUDIT_JOB',
		@enabled=1,
		@notify_level_eventlog=0,
		@notify_level_email=0,
		@notify_level_netsend=0,
		@notify_level_page=0,
		@delete_level=0,
		@description=N'This job stop and start SQL Audit every hour so events are sent to S3 and also enable audit for any new databae created.',
		@category_name=N'[Uncategorized (Local)]',
		@owner_login_name=@sys_usr, @job_id = @jobId OUTPUT
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
/****** Object:  Step [STOP_START SQL AUDIT]    Script Date: 9/23/2021 11:27:23 AM ******/
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'STOP_START SQL AUDIT',
		@step_id=1,
		@cmdexec_success_code=0,
		@on_success_action=4,
		@on_success_step_id=2,
		@on_fail_action=4,
		@on_fail_step_id=3,
		@retry_attempts=0,
		@retry_interval=0,
		@os_run_priority=0, @subsystem=N'TSQL',
		@command=N'-- STOP SQL NATIVE AUDITING

ALTER SERVER AUDIT [SQL_NATIVE_AUDIT]
WITH (STATE = OFF)

-- START SQL NATIVE AUDITING

ALTER SERVER AUDIT [SQL_NATIVE_AUDIT]
WITH (STATE = ON)',
		@database_name=N'master',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
/****** Object:  Step [ADD AUDIT TO NEW DBS]    Script Date: 9/23/2021 11:27:23 AM ******/
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'ADD AUDIT TO NEW DBS',
		@step_id=2,
		@cmdexec_success_code=0,
		@on_success_action=1,
		@on_success_step_id=0,
		@on_fail_action=4,
		@on_fail_step_id=3,
		@retry_attempts=0,
		@retry_interval=0,
		@os_run_priority=0, @subsystem=N'TSQL',
		@command=N'CREATE TABLE ##DB_AUDIT
(
DBNAME	VARCHAR(255),
FLAG	BIT
)

DECLARE @DBNAME VARCHAR(255)
DECLARE @command VARCHAR(2000)

DECLARE DBS CURSOR FOR
SELECT NAME FROM sys.databases WHERE NAME NOT IN (''master'',''tempdb'',''model'',''msdb'',''rdsadmin'')
OPEN DBS
FETCH NEXT FROM DBS INTO @DBNAME
WHILE @@FETCH_STATUS = 0
BEGIN
	SET @command= ''USE ['' + @DBNAME +''];'' +
	''IF EXISTS (SELECT * FROM sys.database_audit_specifications WHERE name = N'''''' + @DBNAME +''_DB_MGMT_SPEC'''')'' +
	''INSERT INTO ##DB_AUDIT VALUES (''''''+ @DBNAME +'''''',1) ELSE INSERT INTO ##DB_AUDIT VALUES (''''''+ @DBNAME +'''''',0);''
	EXECUTE (@command);
FETCH NEXT FROM DBS INTO @DBNAME
END
CLOSE DBS
DEALLOCATE DBS

DECLARE DBS_1 CURSOR FOR
SELECT DBNAME FROM ##DB_AUDIT WHERE FLAG = 0
OPEN DBS_1
FETCH NEXT FROM DBS_1 INTO @DBNAME
WHILE @@FETCH_STATUS = 0
BEGIN
	SET @command= ''USE ['' + @DBNAME +''];'' + ''CREATE DATABASE AUDIT SPECIFICATION [''+@DBNAME+ ''_DB_MGMT_SPEC]''+
	''FOR SERVER AUDIT [SQL_NATIVE_AUDIT]'' +
	''ADD (AUDIT_CHANGE_GROUP),''+
	''ADD (DATABASE_OBJECT_CHANGE_GROUP),''+
	''ADD (DATABASE_OBJECT_OWNERSHIP_CHANGE_GROUP),''+
	''ADD (DATABASE_OWNERSHIP_CHANGE_GROUP),''+
	''ADD (DATABASE_PRINCIPAL_CHANGE_GROUP),''+
	''ADD (DATABASE_PRINCIPAL_IMPERSONATION_GROUP),''+
	''ADD (DATABASE_ROLE_MEMBER_CHANGE_GROUP),''+
	''ADD (SCHEMA_OBJECT_OWNERSHIP_CHANGE_GROUP),''+
	''ADD (DATABASE_OBJECT_PERMISSION_CHANGE_GROUP),''+
	''ADD (DATABASE_PERMISSION_CHANGE_GROUP),''+
	''ADD (SCHEMA_OBJECT_PERMISSION_CHANGE_GROUP)''+
	''WITH (STATE = ON);''
	EXECUTE (@command);
FETCH NEXT FROM DBS_1 INTO @DBNAME
END
CLOSE DBS_1
DEALLOCATE DBS_1

DROP TABLE ##DB_AUDIT',
		@database_name=N'master',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
/****** Object:  Step [GENERATE ERROR IN CASE OF FAILURES]    Script Date: 9/23/2021 11:27:23 AM ******/
EXEC @ReturnCode = msdb.dbo.sp_add_jobstep @job_id=@jobId, @step_name=N'GENERATE ERROR IN CASE OF FAILURES',
		@step_id=3,
		@cmdexec_success_code=0,
		@on_success_action=2,
		@on_success_step_id=0,
		@on_fail_action=2,
		@on_fail_step_id=0,
		@retry_attempts=0,
		@retry_interval=0,
		@os_run_priority=0, @subsystem=N'TSQL',
		@command=N'DECLARE @Var VARCHAR(100)
SELECT ERROR_MESSAGE()
SELECT @Var = "Audit Job Failed. Please Verify"
RAISERROR(@Var, 16,1) WITH LOG
',
		@database_name=N'master',
		@flags=0
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_update_job @job_id = @jobId, @start_step_id = 1
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_add_jobschedule @job_id=@jobId, @name=N'Hourly',
		@enabled=1,
		@freq_type=4,
		@freq_interval=1,
		@freq_subday_type=8,
		@freq_subday_interval=1,
		@freq_relative_interval=0,
		@freq_recurrence_factor=0,
		@active_start_date=20210315,
		@active_end_date=99991231,
		@active_start_time=0,
		@active_end_time=235959
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
EXEC @ReturnCode = msdb.dbo.sp_add_jobserver @job_id = @jobId, @server_name = N'(local)'
IF (@@ERROR <> 0 OR @ReturnCode <> 0) GOTO QuitWithRollback
COMMIT TRANSACTION
GOTO EndSave
QuitWithRollback:
    IF (@@TRANCOUNT > 0) ROLLBACK TRANSACTION
EndSave:

