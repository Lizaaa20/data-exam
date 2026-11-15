USE WWI_Source;

-- ANTES: la línea que vamos a modificar, en el DW
DECLARE @id INT = (SELECT MIN(InvoiceLineID) FROM Sales.InvoiceLines);
SELECT 'DW antes' AS momento, InvoiceLineID, Quantity, NetSalesAmount, LineProfit
FROM WWI_DW.dw.FactSales WHERE InvoiceLineID = @id;

-- (1) Línea MODIFICADA (cantidad +10, importes coherentes)
UPDATE Sales.InvoiceLines
SET Quantity       = Quantity + 10,
    TaxAmount      = ROUND((Quantity + 10) * UnitPrice * TaxRate / 100.0, 2),
    ExtendedPrice  = (Quantity + 10) * UnitPrice + ROUND((Quantity + 10) * UnitPrice * TaxRate / 100.0, 2),
    LineProfit     = LineProfit * (Quantity + 10) / Quantity,
    LastEditedWhen = '2016-06-01T10:00:00'
WHERE InvoiceLineID = @id;

-- (2) Línea NUEVA sobre una factura existente (copia de la última línea)
INSERT Sales.InvoiceLines
    (InvoiceID, StockItemID, Description, PackageTypeID, Quantity, UnitPrice, TaxRate,
     TaxAmount, LineProfit, ExtendedPrice, LastEditedBy, LastEditedWhen)
SELECT TOP 1 InvoiceID, StockItemID, Description, PackageTypeID, Quantity, UnitPrice, TaxRate,
       TaxAmount, LineProfit, ExtendedPrice, LastEditedBy, '2016-06-01T10:00:00'
FROM Sales.InvoiceLines
ORDER BY InvoiceLineID DESC;

SELECT COUNT(*) AS lineas_fuente FROM Sales.InvoiceLines;   -- esperado: 228266


USE WWI_Staging;
SELECT execution_id, pipeline_name, status, rows_read, LEFT(error_detail, 80) AS error
FROM audit.etl_run
WHERE pipeline_name LIKE 'incremental_%'
ORDER BY execution_id DESC;

SELECT * FROM audit.etl_watermark;


-- EVIDENCIA de la carga incremental. Ejecutar DESPUÉS de: python etl/pipeline.py

-- 1. La línea modificada refleja el cambio en el DW (cantidad +10)
DECLARE @id INT = (SELECT MIN(InvoiceLineID) FROM WWI_Source.Sales.InvoiceLines);
SELECT 'Fuente' AS capa, InvoiceLineID, Quantity, Quantity * UnitPrice AS ventas_netas, LineProfit
FROM WWI_Source.Sales.InvoiceLines WHERE InvoiceLineID = @id
UNION ALL
SELECT 'DW', InvoiceLineID, Quantity, NetSalesAmount, LineProfit
FROM WWI_DW.dw.FactSales WHERE InvoiceLineID = @id;

-- 2. Auditoría de las ejecuciones incrementales (incluye las FAILED del error de #inc)
SELECT execution_id, pipeline_name, status, rows_read, rows_inserted, rows_updated,
       watermark_start, watermark_end
FROM WWI_Staging.audit.etl_run
WHERE pipeline_name LIKE 'incremental_%'
ORDER BY execution_id DESC;

-- 3. Watermarks actuales
SELECT * FROM WWI_Staging.audit.etl_watermark;

-- 4. Reconciliación fuente vs DW
SELECT 'Fuente' AS capa, COUNT(*) AS lineas, SUM(Quantity * UnitPrice) AS ventas_netas
FROM WWI_Source.Sales.InvoiceLines
UNION ALL
SELECT 'Data Warehouse', COUNT(*), SUM(NetSalesAmount) FROM WWI_DW.dw.FactSales;