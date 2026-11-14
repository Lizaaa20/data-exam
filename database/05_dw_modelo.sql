USE WWI_DW;
GO
IF SCHEMA_ID('dw') IS NULL EXEC('CREATE SCHEMA dw');
GO

-- Orden de borrado: primero el hecho, luego las dimensiones
DROP TABLE IF EXISTS dw.FactSales;
DROP TABLE IF EXISTS dw.DimCustomer;
DROP TABLE IF EXISTS dw.DimProduct;
DROP TABLE IF EXISTS dw.DimSalesperson;
DROP TABLE IF EXISTS dw.DimDate;
GO

-- DimDate
CREATE TABLE dw.DimDate (
    DateKey      INT          NOT NULL PRIMARY KEY,   -- yyyymmdd
    FullDate     DATE         NOT NULL UNIQUE,
    DayOfMonth   TINYINT      NOT NULL,
    DayName      NVARCHAR(10) NOT NULL,
    MonthNumber  TINYINT      NOT NULL,
    MonthName    NVARCHAR(10) NOT NULL,
    QuarterNum   TINYINT      NOT NULL,
    YearNum      SMALLINT     NOT NULL,
    YearMonth    CHAR(7)      NOT NULL,                -- yyyy-mm
    IsWeekend    BIT          NOT NULL
);

-- DimCustomer (SCD Tipo 2)
CREATE TABLE dw.DimCustomer (
    CustomerKey          INT IDENTITY(1,1) PRIMARY KEY,
    CustomerID           INT           NOT NULL,       -- clave natural
    CustomerName         NVARCHAR(100) NOT NULL,
    CustomerCategory     NVARCHAR(50)  NOT NULL,
    BuyingGroup          NVARCHAR(50)  NOT NULL,
    CityName             NVARCHAR(50)  NOT NULL,
    StateProvinceName    NVARCHAR(50)  NOT NULL,
    CountryName          NVARCHAR(60)  NOT NULL,
    Region               NVARCHAR(30)  NOT NULL,
    ValidFrom            DATE          NOT NULL,
    ValidTo              DATE          NOT NULL,       -- 9999-12-31 si es vigente
    IsCurrent            BIT           NOT NULL
);
CREATE INDEX IX_DimCustomer_Natural ON dw.DimCustomer (CustomerID, IsCurrent);

-- DimProduct (Tipo 1, categoría principal)
CREATE TABLE dw.DimProduct (
    ProductKey       INT IDENTITY(1,1) PRIMARY KEY,
    StockItemID      INT           NOT NULL UNIQUE,    -- clave natural
    StockItemName    NVARCHAR(100) NOT NULL,
    Brand            NVARCHAR(50)  NOT NULL,
    ColorName        NVARCHAR(20)  NOT NULL,
    Size             NVARCHAR(20)  NOT NULL,
    PrimaryCategory  NVARCHAR(50)  NOT NULL
);

-- DimSalesperson (Tipo 1)
CREATE TABLE dw.DimSalesperson (
    SalespersonKey  INT IDENTITY(1,1) PRIMARY KEY,
    PersonID        INT           NOT NULL UNIQUE,     -- clave natural
    FullName        NVARCHAR(50)  NOT NULL
);

-- FactSales: una fila por línea de factura
CREATE TABLE dw.FactSales (
    SalesKey         BIGINT IDENTITY(1,1) PRIMARY KEY,
    DateKey          INT            NOT NULL REFERENCES dw.DimDate(DateKey),
    CustomerKey      INT            NOT NULL REFERENCES dw.DimCustomer(CustomerKey),
    ProductKey       INT            NOT NULL REFERENCES dw.DimProduct(ProductKey),
    SalespersonKey   INT            NOT NULL REFERENCES dw.DimSalesperson(SalespersonKey),
    InvoiceID        INT            NOT NULL,          -- dimensión degenerada
    InvoiceLineID    INT            NOT NULL UNIQUE,   -- evita duplicados (idempotencia)
    Quantity         INT            NOT NULL,
    UnitPrice        DECIMAL(18,2)  NOT NULL,          -- no aditiva
    NetSalesAmount   DECIMAL(18,2)  NOT NULL,          -- Quantity * UnitPrice
    TaxAmount        DECIMAL(18,2)  NOT NULL,
    ExtendedPrice    DECIMAL(18,2)  NOT NULL,          -- con impuesto
    LineProfit       DECIMAL(18,2)  NOT NULL
);
CREATE INDEX IX_FactSales_Date     ON dw.FactSales (DateKey);
CREATE INDEX IX_FactSales_Customer ON dw.FactSales (CustomerKey);
CREATE INDEX IX_FactSales_Product  ON dw.FactSales (ProductKey);
GO

-- Miembros "Desconocido" (clave -1)
SET IDENTITY_INSERT dw.DimCustomer ON;
INSERT dw.DimCustomer (CustomerKey, CustomerID, CustomerName, CustomerCategory, BuyingGroup,
                       CityName, StateProvinceName, CountryName, Region, ValidFrom, ValidTo, IsCurrent)
VALUES (-1, -1, N'Desconocido', N'Desconocido', N'Desconocido', N'Desconocido', N'Desconocido',
        N'Desconocido', N'Desconocido', '1900-01-01', '9999-12-31', 1);
SET IDENTITY_INSERT dw.DimCustomer OFF;

SET IDENTITY_INSERT dw.DimProduct ON;
INSERT dw.DimProduct (ProductKey, StockItemID, StockItemName, Brand, ColorName, Size, PrimaryCategory)
VALUES (-1, -1, N'Desconocido', N'Desconocido', N'Desconocido', N'Desconocido', N'Desconocido');
SET IDENTITY_INSERT dw.DimProduct OFF;

SET IDENTITY_INSERT dw.DimSalesperson ON;
INSERT dw.DimSalesperson (SalespersonKey, PersonID, FullName) VALUES (-1, -1, N'Desconocido');
SET IDENTITY_INSERT dw.DimSalesperson OFF;
GO

-- Poblar DimDate: 2013-01-01 a 2016-12-31
WITH d AS (
    SELECT CAST('2013-01-01' AS DATE) AS f
    UNION ALL
    SELECT DATEADD(DAY, 1, f) FROM d WHERE f < '2016-12-31'
)
INSERT dw.DimDate (DateKey, FullDate, DayOfMonth, DayName, MonthNumber, MonthName,
                   QuarterNum, YearNum, YearMonth, IsWeekend)
SELECT CONVERT(INT, FORMAT(f, 'yyyyMMdd')), f, DAY(f), DATENAME(WEEKDAY, f), MONTH(f),
       DATENAME(MONTH, f), DATEPART(QUARTER, f), YEAR(f), FORMAT(f, 'yyyy-MM'),
       CASE WHEN DATEPART(WEEKDAY, f) IN (1, 7) THEN 1 ELSE 0 END
FROM d
OPTION (MAXRECURSION 2000);
GO

SELECT COUNT(*) AS dias FROM dw.DimDate;   -- esperado: 1461


USE WWI_DW;
SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID('dw') ORDER BY name;
SELECT 'DimCustomer' AS tabla, COUNT(*) AS filas FROM dw.DimCustomer
UNION ALL SELECT 'DimProduct', COUNT(*) FROM dw.DimProduct
UNION ALL SELECT 'DimSalesperson', COUNT(*) FROM dw.DimSalesperson
UNION ALL SELECT 'DimDate', COUNT(*) FROM dw.DimDate;