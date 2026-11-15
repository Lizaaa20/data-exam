DECLARE @desde DATE = '2013-01-01', @hasta DATE = '2016-12-31';

SELECT SUM(l.Quantity * l.UnitPrice)                                          AS ventas_netas,
       SUM(l.LineProfit)                                                      AS utilidad,
       SUM(l.LineProfit) * 100.0 / NULLIF(SUM(l.Quantity * l.UnitPrice), 0)   AS margen_pct,
       SUM(l.Quantity)                                                        AS unidades,
       COUNT(DISTINCT l.InvoiceID)                                            AS facturas,
       SUM(l.Quantity * l.UnitPrice) / COUNT(DISTINCT l.InvoiceID)            AS ticket_promedio
FROM WWI_Source.Sales.InvoiceLines l
JOIN WWI_Source.Sales.Invoices i ON i.InvoiceID = l.InvoiceID
WHERE i.InvoiceDate BETWEEN @desde AND @hasta;



DECLARE @desde DATE = '2014-01-01', @hasta DATE = '2014-12-31';

WITH cat AS (
    SELECT StockItemID, MAX(StockGroupID) AS StockGroupID
    FROM WWI_Source.Warehouse.StockItemStockGroups
    GROUP BY StockItemID
)
SELECT SUM(l.Quantity * l.UnitPrice)                                          AS ventas_netas,
       SUM(l.LineProfit)                                                      AS utilidad,
       SUM(l.LineProfit) * 100.0 / NULLIF(SUM(l.Quantity * l.UnitPrice), 0)   AS margen_pct,
       SUM(l.Quantity)                                                        AS unidades,
       COUNT(DISTINCT l.InvoiceID)                                            AS facturas,
       SUM(l.Quantity * l.UnitPrice) / NULLIF(COUNT(DISTINCT l.InvoiceID), 0) AS ticket_promedio
FROM WWI_Source.Sales.InvoiceLines l
JOIN WWI_Source.Sales.Invoices i       ON i.InvoiceID = l.InvoiceID
JOIN cat                               ON cat.StockItemID = l.StockItemID
JOIN WWI_Source.Warehouse.StockGroups g ON g.StockGroupID = cat.StockGroupID
WHERE g.StockGroupName = 'Clothing'
  AND i.InvoiceDate BETWEEN @desde AND @hasta;