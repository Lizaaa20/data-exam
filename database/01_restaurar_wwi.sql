RESTORE FILELISTONLY
FROM DISK = N'C:\Program Files\Microsoft SQL Server\MSSQL16.MSSQLSERVER\MSSQL\Backup\WideWorldImporters-Full.bak';

USE master;
GO
DECLARE @data NVARCHAR(260) = CONVERT(NVARCHAR(260), SERVERPROPERTY('InstanceDefaultDataPath'));
DECLARE @log  NVARCHAR(260) = CONVERT(NVARCHAR(260), SERVERPROPERTY('InstanceDefaultLogPath'));

DECLARE @sql NVARCHAR(MAX) = N'
RESTORE DATABASE WWI_Source
FROM DISK = N''C:\Program Files\Microsoft SQL Server\MSSQL16.MSSQLSERVER\MSSQL\Backup\WideWorldImporters-Full.bak''
WITH
  MOVE N''WWI_Primary''         TO N''' + @data + N'WWI_Source.mdf'',
  MOVE N''WWI_UserData''        TO N''' + @data + N'WWI_Source_UserData.ndf'',
  MOVE N''WWI_Log''             TO N''' + @log  + N'WWI_Source.ldf'',
  MOVE N''WWI_InMemory_Data_1'' TO N''' + @data + N'WWI_Source_InMemory_Data_1'',
  STATS = 10, REPLACE;';
EXEC sp_executesql @sql;
GO

IF DB_ID('WWI_Staging') IS NULL CREATE DATABASE WWI_Staging;
IF DB_ID('WWI_DW')      IS NULL CREATE DATABASE WWI_DW;
GO