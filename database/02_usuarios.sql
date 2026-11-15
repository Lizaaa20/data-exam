USE master;
GO
CREATE LOGIN etl_reader WITH PASSWORD = '<CLAVE_READER>', CHECK_POLICY = OFF;
CREATE LOGIN etl_writer WITH PASSWORD = '<CLAVE_WRITER>', CHECK_POLICY = OFF;
GO

-- Solo lectura sobre la fuente
USE WWI_Source;
CREATE USER etl_reader FOR LOGIN etl_reader;
ALTER ROLE db_datareader ADD MEMBER etl_reader;
GO

-- Lectura/escritura/DDL sobre staging y DW
USE WWI_Staging;
CREATE USER etl_writer FOR LOGIN etl_writer;
ALTER ROLE db_datareader ADD MEMBER etl_writer;
ALTER ROLE db_datawriter ADD MEMBER etl_writer;
ALTER ROLE db_ddladmin   ADD MEMBER etl_writer;
GO

USE WWI_DW;
CREATE USER etl_writer FOR LOGIN etl_writer;
ALTER ROLE db_datareader ADD MEMBER etl_writer;
ALTER ROLE db_datawriter ADD MEMBER etl_writer;
ALTER ROLE db_ddladmin   ADD MEMBER etl_writer;
GO

USE master;
GO
IF SUSER_ID('api_reader') IS NULL
    CREATE LOGIN api_reader WITH PASSWORD = '<CLAVE_READER>', CHECK_POLICY = OFF;
ELSE
    ALTER LOGIN api_reader WITH PASSWORD = '<CLAVE_READER>';
ALTER LOGIN api_reader ENABLE;
GO
USE WWI_DW;
IF USER_ID('api_reader') IS NULL CREATE USER api_reader FOR LOGIN api_reader;
ALTER ROLE db_datareader ADD MEMBER api_reader;
GO
USE WWI_Staging;
IF USER_ID('api_reader') IS NULL CREATE USER api_reader FOR LOGIN api_reader;
GRANT SELECT ON audit.etl_run TO api_reader;
GO

