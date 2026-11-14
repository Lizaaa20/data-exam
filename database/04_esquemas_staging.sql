USE WWI_Staging;
GO
IF SCHEMA_ID('raw')        IS NULL EXEC('CREATE SCHEMA raw');
IF SCHEMA_ID('clean')      IS NULL EXEC('CREATE SCHEMA clean');
IF SCHEMA_ID('ready')      IS NULL EXEC('CREATE SCHEMA ready');
IF SCHEMA_ID('audit')      IS NULL EXEC('CREATE SCHEMA audit');
IF SCHEMA_ID('quarantine') IS NULL EXEC('CREATE SCHEMA quarantine');
GO

USE WWI_DW;
GO
IF SCHEMA_ID('dw') IS NULL EXEC('CREATE SCHEMA dw');
GO

SELECT 'WWI_Staging' AS base, name AS esquema FROM WWI_Staging.sys.schemas
WHERE name IN ('raw','clean','ready','audit','quarantine')
UNION ALL
SELECT 'WWI_DW', name FROM WWI_DW.sys.schemas WHERE name = 'dw';