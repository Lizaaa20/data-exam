USE WWI_Staging;
GO
-- SIMULACIÓN: datos defectuosos para probar reglas de calidad y cuarentena.
-- Todas las filas llevan _execution_id = -1 para poder borrarlas luego.

DECLARE @cust INT = (SELECT TOP 1 CustomerID  FROM raw.Sales_Customers   ORDER BY CustomerID);
DECLARE @prod INT = (SELECT TOP 1 StockItemID FROM raw.Warehouse_StockItems ORDER BY StockItemID);
DECLARE @pers INT = (SELECT TOP 1 PersonID    FROM raw.Application_People ORDER BY PersonID);

-- Facturas de prueba
INSERT raw.Sales_Invoices (InvoiceID, CustomerID, OrderID, SalespersonPersonID, InvoiceDate, LastEditedWhen, _execution_id)
VALUES (900001, @cust, 1, @pers, '2016-01-15', '2016-05-31 12:00', -1),   -- válida
       (900002, @cust, 1, @pers, '2030-01-01', '2016-05-31 12:00', -1),   -- fecha futura
       (900003, 99999, 1, @pers, '2016-01-15', '2016-05-31 12:00', -1);   -- cliente inexistente

-- Líneas de prueba
INSERT raw.Sales_InvoiceLines
    (InvoiceLineID, InvoiceID, StockItemID, Quantity, UnitPrice, TaxAmount, LineProfit, ExtendedPrice, LastEditedWhen, _execution_id)
VALUES
 (900001, 900001, @prod, -5, 10.00, 0.00, 0.00, -50.00, '2016-05-31 12:00', -1),   -- CANTIDAD_POSITIVA
 (900002, 900001, @prod,  1,-10.00, 0.00, 0.00, -10.00, '2016-05-31 12:00', -1),   -- PRECIO_NO_NEGATIVO
 (900003, 900002, @prod,  1, 10.00, 1.50, 2.00,  11.50, '2016-05-31 12:00', -1),   -- FECHA_VALIDA
 (900004, 900003, @prod,  1, 10.00, 1.50, 2.00,  11.50, '2016-05-31 12:00', -1),   -- CLIENTE_EXISTE
 (900005, 900001, 99999,  1, 10.00, 1.50, 2.00,  11.50, '2016-05-31 12:00', -1),   -- PRODUCTO_EXISTE
 (900006, 900001, @prod,  2, 10.00, 3.00, 4.00, 999.00, '2016-05-31 12:00', -1);   -- válida, pero TOTAL incoherente (solo se marca)

-- Duplicado de una línea real (más antiguo, para que sobreviva la original)
INSERT raw.Sales_InvoiceLines
    (InvoiceLineID, InvoiceID, StockItemID, Quantity, UnitPrice, TaxAmount, LineProfit, ExtendedPrice, LastEditedWhen, _execution_id)
SELECT TOP 1 InvoiceLineID, InvoiceID, StockItemID, Quantity, UnitPrice, TaxAmount, LineProfit, ExtendedPrice,
       '2000-01-01', -1
FROM raw.Sales_InvoiceLines
WHERE _execution_id > 0
ORDER BY InvoiceLineID;                                                            -- LINEA_UNICA
GO

SELECT COUNT(*) AS lineas_en_raw FROM raw.Sales_InvoiceLines;   -- esperado: 228272

USE WWI_Staging;

-- Qué se rechazó y por qué regla
SELECT rule_name, COUNT(*) AS filas
FROM quarantine.rejected_rows
WHERE execution_id = (SELECT MAX(execution_id) FROM audit.etl_run WHERE pipeline_name = 'clean_sales')
GROUP BY rule_name
ORDER BY rule_name;

-- Detalle de cada rechazo
SELECT source_key, rule_name, detail
FROM quarantine.rejected_rows
WHERE execution_id = (SELECT MAX(execution_id) FROM audit.etl_run WHERE pipeline_name = 'clean_sales')
ORDER BY rule_name;

-- La línea marcada (pasa, pero con flag)
SELECT InvoiceLineID, ExtendedPrice, Quantity * UnitPrice + TaxAmount AS total_esperado, FlagTotalIncoherente
FROM clean.Sales_InvoiceLines
WHERE FlagTotalIncoherente = 1;