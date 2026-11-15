USE master;
GO
IF SUSER_ID('api_reader') IS NULL
    CREATE LOGIN api_reader WITH PASSWORD = '<CLAVE_API>', CHECK_POLICY = OFF;
GO
USE WWI_DW;
IF USER_ID('api_reader') IS NULL CREATE USER api_reader FOR LOGIN api_reader;
ALTER ROLE db_datareader ADD MEMBER api_reader;
GO
-- Solo para mostrar la fecha de la última carga exitosa
USE WWI_Staging;
IF USER_ID('api_reader') IS NULL CREATE USER api_reader FOR LOGIN api_reader;
GRANT SELECT ON audit.etl_run TO api_reader;
GO