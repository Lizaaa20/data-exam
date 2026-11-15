USE WWI_DW;
GO
IF OBJECT_ID('dw.ModelRun') IS NULL
CREATE TABLE dw.ModelRun (
    ModelVersion     NVARCHAR(40)   NOT NULL PRIMARY KEY,
    ModelName        NVARCHAR(40)   NOT NULL,
    TrainedAt        DATETIME2(0)   NOT NULL,
    TrainRange       NVARCHAR(40)   NOT NULL,
    TestRange        NVARCHAR(40)   NOT NULL,
    Params           NVARCHAR(MAX)  NULL,
    MaeTest          DECIMAL(18,2)  NOT NULL,
    RmseTest         DECIMAL(18,2)  NOT NULL,
    SmapeTest        DECIMAL(9,2)   NOT NULL,
    BaselineName     NVARCHAR(40)   NOT NULL,
    BaselineMaeTest  DECIMAL(18,2)  NOT NULL
);

IF OBJECT_ID('dw.PredictedSales') IS NULL
CREATE TABLE dw.PredictedSales (
    PredictionKey   BIGINT IDENTITY(1,1) PRIMARY KEY,
    ModelVersion    NVARCHAR(40)  NOT NULL REFERENCES dw.ModelRun(ModelVersion),
    PredictionDate  DATE          NOT NULL,
    Category        NVARCHAR(50)  NOT NULL,
    TargetMonth     CHAR(7)       NOT NULL,   -- yyyy-mm
    HorizonMonths   TINYINT       NOT NULL,
    PredictedSales  DECIMAL(18,2) NOT NULL,
    CONSTRAINT UQ_PredictedSales UNIQUE (ModelVersion, Category, TargetMonth)
);
GO


SELECT * FROM WWI_DW.dw.ModelRun;

SELECT Category, TargetMonth, HorizonMonths, PredictedSales
FROM WWI_DW.dw.PredictedSales
WHERE ModelVersion = (SELECT TOP 1 ModelVersion FROM WWI_DW.dw.ModelRun ORDER BY TrainedAt DESC)
ORDER BY Category, TargetMonth;


WITH hist AS (
  SELECT p.PrimaryCategory AS categoria, d.YearMonth AS mes, SUM(f.NetSalesAmount) AS ventas
  FROM WWI_DW.dw.FactSales f
  JOIN WWI_DW.dw.DimDate d    ON d.DateKey = f.DateKey
  JOIN WWI_DW.dw.DimProduct p ON p.ProductKey = f.ProductKey
  WHERE d.YearMonth BETWEEN '2015-12' AND '2016-05'
  GROUP BY p.PrimaryCategory, d.YearMonth
)
SELECT h.categoria,
       AVG(h.ventas) AS promedio_ultimos_6_meses,
       (SELECT AVG(ps.PredictedSales) FROM WWI_DW.dw.PredictedSales ps
        WHERE ps.Category = h.categoria
          AND ps.ModelVersion = (SELECT TOP 1 ModelVersion FROM WWI_DW.dw.ModelRun ORDER BY TrainedAt DESC)
       ) AS promedio_pronostico
FROM hist h
GROUP BY h.categoria
ORDER BY h.categoria;

WITH m AS (
  SELECT p.PrimaryCategory AS categoria, d.YearMonth AS mes, SUM(f.NetSalesAmount) AS ventas
  FROM WWI_DW.dw.FactSales f
  JOIN WWI_DW.dw.DimDate d    ON d.DateKey = f.DateKey
  JOIN WWI_DW.dw.DimProduct p ON p.ProductKey = f.ProductKey
  WHERE d.YearMonth BETWEEN '2015-06' AND '2015-08'
  GROUP BY p.PrimaryCategory, d.YearMonth
),
rec AS (
  SELECT p.PrimaryCategory AS categoria, SUM(f.NetSalesAmount) / 6.0 AS prom_ult_6m
  FROM WWI_DW.dw.FactSales f
  JOIN WWI_DW.dw.DimDate d    ON d.DateKey = f.DateKey
  JOIN WWI_DW.dw.DimProduct p ON p.ProductKey = f.ProductKey
  WHERE d.YearMonth BETWEEN '2015-12' AND '2016-05'
  GROUP BY p.PrimaryCategory
),
pron AS (
  SELECT Category AS categoria, AVG(PredictedSales) AS prom_pronostico
  FROM WWI_DW.dw.PredictedSales
  WHERE ModelVersion = (SELECT TOP 1 ModelVersion FROM WWI_DW.dw.ModelRun ORDER BY TrainedAt DESC)
  GROUP BY Category
)
SELECT c.v AS categoria,
       (SELECT SUM(ventas) / 3.0 FROM m WHERE m.categoria = c.v) AS prom_jun_ago_2015,
       (SELECT COUNT(*) FROM m WHERE m.categoria = c.v)          AS meses_con_ventas,
       rec.prom_ult_6m,
       pron.prom_pronostico
FROM (SELECT DISTINCT PrimaryCategory AS v FROM WWI_DW.dw.DimProduct WHERE ProductKey <> -1) c
LEFT JOIN rec  ON rec.categoria  = c.v
LEFT JOIN pron ON pron.categoria = c.v
ORDER BY c.v;







-- 1. Variación interanual de los últimos 6 meses por categoría
SELECT p.PrimaryCategory AS categoria,
       SUM(CASE WHEN d.YearMonth BETWEEN '2014-12' AND '2015-05' THEN f.NetSalesAmount END) AS dic14_may15,
       SUM(CASE WHEN d.YearMonth BETWEEN '2015-12' AND '2016-05' THEN f.NetSalesAmount END) AS dic15_may16,
       ROUND((SUM(CASE WHEN d.YearMonth BETWEEN '2015-12' AND '2016-05' THEN f.NetSalesAmount END)
            - SUM(CASE WHEN d.YearMonth BETWEEN '2014-12' AND '2015-05' THEN f.NetSalesAmount END)) * 100.0
            / NULLIF(SUM(CASE WHEN d.YearMonth BETWEEN '2014-12' AND '2015-05' THEN f.NetSalesAmount END), 0), 1) AS variacion_pct
FROM WWI_DW.dw.FactSales f
JOIN WWI_DW.dw.DimDate d    ON d.DateKey = f.DateKey
JOIN WWI_DW.dw.DimProduct p ON p.ProductKey = f.ProductKey
WHERE d.YearMonth BETWEEN '2014-12' AND '2016-05' AND p.ProductKey <> -1
GROUP BY p.PrimaryCategory
ORDER BY p.PrimaryCategory;

-- 2. Meses con ventas de Novelty Items desde 2015-06
SELECT d.YearMonth AS mes, SUM(f.NetSalesAmount) AS ventas
FROM WWI_DW.dw.FactSales f
JOIN WWI_DW.dw.DimDate d    ON d.DateKey = f.DateKey
JOIN WWI_DW.dw.DimProduct p ON p.ProductKey = f.ProductKey
WHERE p.PrimaryCategory = 'Novelty Items' AND d.YearMonth >= '2015-06'
GROUP BY d.YearMonth
ORDER BY d.YearMonth;

SELECT ModelVersion, ModelName, TrainRange, TestRange, MaeTest, BaselineName, BaselineMaeTest
FROM WWI_DW.dw.ModelRun ORDER BY TrainedAt DESC;