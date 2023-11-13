CREATE BIGFILE TABLESPACE AUDIT_TBLSPACE DATAFILE SIZE 100M AUTOEXTEND ON NEXT 100M MAXSIZE UNLIMITED
begin DBMS_AUDIT_MGMT.SET_AUDIT_TRAIL_LOCATION(audit_trail_type => DBMS_AUDIT_MGMT.AUDIT_TRAIL_AUD_STD, audit_trail_location_value => 'AUDIT_TBLSPACE');end;
begin DBMS_AUDIT_MGMT.SET_AUDIT_TRAIL_LOCATION(audit_trail_type => DBMS_AUDIT_MGMT.AUDIT_TRAIL_UNIFIED, audit_trail_location_value => 'AUDIT_TBLSPACE');end;
begin DBMS_AUDIT_MGMT.SET_AUDIT_TRAIL_LOCATION(audit_trail_type => DBMS_AUDIT_MGMT.AUDIT_TRAIL_FGA_STD, audit_trail_location_value => 'AUDIT_TBLSPACE');end;
declare v_dbversion varchar2(10); v_paudit varchar2(1000); begin select substr(version,0,4) into v_dbversion from v$instance; if v_dbversion <> '12.1' then v_paudit := 'begin DBMS_AUDIT_MGMT.ALTER_PARTITION_INTERVAL (interval_number => 1,interval_frequency => ''DAY''); end;'; execute immediate v_paudit; end if; end;

AUDIT CREATE ANY PROCEDURE
AUDIT CREATE ANY TABLE
AUDIT CREATE ANY TRIGGER
AUDIT CREATE DATABASE LINK
AUDIT CREATE PROCEDURE
AUDIT CREATE SESSION
AUDIT CREATE USER
AUDIT CREATE VIEW
AUDIT CREATE ANY CLUSTER
AUDIT CREATE ANY CONTEXT
AUDIT CREATE ANY DIMENSION
AUDIT CREATE ANY DIRECTORY
AUDIT CREATE ANY EVALUATION CONTEXT
AUDIT CREATE ANY INDEX
AUDIT CREATE ANY INDEXTYPE
AUDIT CREATE ANY JOB
AUDIT CREATE ANY LIBRARY
AUDIT CREATE ANY MATERIALIZED VIEW
AUDIT CREATE ANY OPERATOR
AUDIT CREATE ANY OUTLINE
AUDIT CREATE ANY RULE SET
AUDIT CREATE ANY RULE
AUDIT CREATE ANY SEQUENCE
AUDIT CREATE ANY SQL PROFILE
AUDIT CREATE ANY SYNONYM
AUDIT CREATE ANY TYPE
AUDIT CREATE ANY VIEW
AUDIT CREATE EXTERNAL JOB
AUDIT CREATE PUBLIC DATABASE LINK
AUDIT CREATE PROFILE
AUDIT CREATE ROLE
AUDIT ALTER ANY TABLE
AUDIT ALTER DATABASE
AUDIT ALTER PROFILE
AUDIT ALTER SYSTEM
AUDIT ALTER ANY PROCEDURE
AUDIT ALTER TABLE
AUDIT ALTER USER
AUDIT ALTER ANY ROLE
AUDIT DROP ANY TABLE
AUDIT DROP ANY TRIGGER
AUDIT DROP PROFILE
AUDIT DROP USER
AUDIT DROP ANY PROCEDURE
AUDIT GRANT ANY OBJECT PRIVILEGE
AUDIT GRANT ANY PRIVILEGE
AUDIT GRANT ANY ROLE
AUDIT GRANT PROCEDURE
AUDIT GRANT SEQUENCE
AUDIT GRANT TABLE
AUDIT INDEX
AUDIT LOCK TABLE
AUDIT PROCEDURE
AUDIT PROFILE
AUDIT PUBLIC DATABASE LINK
AUDIT DATABASE LINK
AUDIT PUBLIC SYNONYM
AUDIT ROLE
AUDIT SEQUENCE
AUDIT audit ANY
AUDIT SYNONYM
AUDIT BECOME USER
AUDIT CLUSTER
AUDIT EXECUTE ANY PROCEDURE
AUDIT SYSTEM GRANT
AUDIT TABLE
AUDIT DIRECTORY
AUDIT TABLESPACE
AUDIT TRIGGER
AUDIT USER
AUDIT VIEW
AUDIT ADMINISTER DATABASE TRIGGER
AUDIT audit SYSTEM
AUDIT RESTRICTED SESSION
AUDIT SYSTEM AUDIT
AUDIT EXEMPT ACCESS POLICY
AUDIT MATERIALIZED VIEW
AUDIT INSERT ANY TABLE
AUDIT UPDATE ANY TABLE
AUDIT DELETE ANY TABLE
AUDIT DELETE TABLE BY {{ MASTER_USERNAME }}
AUDIT DELETE TABLE BY RDSADMIN
AUDIT DELETE TABLE BY SYSTEM
AUDIT INSERT TABLE BY {{ MASTER_USERNAME }}
AUDIT INSERT TABLE BY RDSADMIN
AUDIT INSERT TABLE BY SYSTEM
AUDIT UPDATE TABLE BY {{ MASTER_USERNAME }}
AUDIT UPDATE TABLE BY RDSADMIN
AUDIT UPDATE TABLE BY SYSTEM
{% if not (VERSION.startswith('12.') or VERSION.startswith('19.')) %}
AUDIT TRUNCATE
{% endif %}

BEGIN IF  NOT DBMS_AUDIT_MGMT.IS_CLEANUP_INITIALIZED(DBMS_AUDIT_MGMT.AUDIT_TRAIL_AUD_STD) THEN    DBMS_AUDIT_MGMT.INIT_CLEANUP(       audit_trail_type          => DBMS_AUDIT_MGMT.AUDIT_TRAIL_AUD_STD,       default_cleanup_interval  => 24 /* hours */); END IF; IF    NOT DBMS_AUDIT_MGMT.IS_CLEANUP_INITIALIZED(DBMS_AUDIT_MGMT.AUDIT_TRAIL_FGA_STD) THEN    DBMS_AUDIT_MGMT.INIT_CLEANUP(       audit_trail_type          => DBMS_AUDIT_MGMT.AUDIT_TRAIL_FGA_STD,       default_cleanup_interval  => 24 /* hours */); END IF; END;

DECLARE     job_already_exists EXCEPTION;     PRAGMA EXCEPTION_INIT( job_already_exists, -27477 ); BEGIN sys.dbms_scheduler.create_job( job_name => '"UNIFIED_AUDIT"', job_type => 'PLSQL_BLOCK', job_action => 'begin -- first load any spillover OS files DBMS_AUDIT_MGMT.LOAD_UNIFIED_AUDIT_FILES(); -- then set the last archive TS for all trails (file trails require local server time zone, db trails utc) dbms_audit_mgmt.set_last_archive_timestamp(audit_trail_type=>dbms_audit_mgmt.audit_trail_unified,last_archive_time=> trunc(sys_extract_utc(systimestamp - interval ''30'' DAY))); dbms_audit_mgmt.set_last_archive_timestamp(audit_trail_type=>dbms_audit_mgmt.audit_trail_aud_std,last_archive_time=> trunc(sys_extract_utc(systimestamp - interval ''30'' DAY))); dbms_audit_mgmt.set_last_archive_timestamp(audit_trail_type=>dbms_audit_mgmt.audit_trail_fga_std,last_archive_time=> trunc(sys_extract_utc(systimestamp - interval ''30'' DAY))); dbms_audit_mgmt.set_last_archive_timestamp(audit_trail_type=>dbms_audit_mgmt.audit_trail_os,last_archive_time=> trunc(systimestamp - interval ''30'' DAY)); dbms_audit_mgmt.set_last_archive_timestamp(audit_trail_type=>dbms_audit_mgmt.audit_trail_xml,last_archive_time=> trunc(systimestamp - interval ''30'' DAY)); -- then we clean up all dbms_audit_mgmt.clean_audit_trail(audit_trail_type=>dbms_audit_mgmt.audit_trail_all,use_last_arch_timestamp=>true); end;', repeat_interval => 'FREQ=DAILY;BYHOUR=0;BYMINUTE=0', start_date => systimestamp, job_class => '"DEFAULT_JOB_CLASS"', comments => 'Unified Audit Cleanup Job', auto_drop => FALSE, enabled => TRUE); EXCEPTION when job_already_exists then    null; END;