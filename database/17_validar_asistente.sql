-- 1. Crecimiento por categoría (contrasta las respuestas 2 y 3 del asistente)
-- (la consulta de crecimiento por categoría de la captura)

SELECT SUM(l.Quantity * l.UnitPrice) AS ventas, SUM(l.LineProfit) AS utilidad,
       SUM(l.LineProfit) * 100.0 / SUM(l.Quantity * l.UnitPrice) AS margen_pct
FROM WWI_Source.Sales.InvoiceLines l
JOIN WWI_Source.Sales.Invoices i ON i.InvoiceID = l.InvoiceID
JOIN (SELECT StockItemID, MAX(StockGroupID) AS g
      FROM WWI_Source.Warehouse.StockItemStockGroups GROUP BY StockItemID) c ON c.StockItemID = l.StockItemID
WHERE c.g = 2 AND i.InvoiceDate BETWEEN '2016-03-01' AND '2016-05-31';

-- 2. Clothing, último trimestre (contrasta la respuesta 8)
-- (la consulta de Clothing de la captura)

SELECT p.PrimaryCategory AS categoria,
       SUM(CASE WHEN d.FullDate BETWEEN '2015-06-01' AND '2016-05-31' THEN f.NetSalesAmount END) AS actual,
       SUM(CASE WHEN d.FullDate BETWEEN '2014-05-31' AND '2015-05-31' THEN f.NetSalesAmount END) AS anterior,
       ROUND((SUM(CASE WHEN d.FullDate BETWEEN '2015-06-01' AND '2016-05-31' THEN f.NetSalesAmount END)
            - SUM(CASE WHEN d.FullDate BETWEEN '2014-05-31' AND '2015-05-31' THEN f.NetSalesAmount END)) * 100.0
            / NULLIF(SUM(CASE WHEN d.FullDate BETWEEN '2014-05-31' AND '2015-05-31' THEN f.NetSalesAmount END), 0), 1) AS crecimiento_pct
FROM WWI_DW.dw.FactSales f
JOIN WWI_DW.dw.DimDate d    ON d.DateKey = f.DateKey
JOIN WWI_DW.dw.DimProduct p ON p.ProductKey = f.ProductKey
WHERE p.ProductKey <> -1
GROUP BY p.PrimaryCategory
ORDER BY crecimiento_pct DESC;

SELECT TOP 8 c.StateProvinceName AS estado,
       SUM(CASE WHEN d.FullDate BETWEEN '2015-06-01' AND '2016-05-31' THEN f.NetSalesAmount END) AS actual,
       SUM(CASE WHEN d.FullDate BETWEEN '2014-05-31' AND '2015-05-31' THEN f.NetSalesAmount END) AS anterior,
       ROUND((SUM(CASE WHEN d.FullDate BETWEEN '2015-06-01' AND '2016-05-31' THEN f.NetSalesAmount END)
            - SUM(CASE WHEN d.FullDate BETWEEN '2014-05-31' AND '2015-05-31' THEN f.NetSalesAmount END)) * 100.0
            / NULLIF(SUM(CASE WHEN d.FullDate BETWEEN '2014-05-31' AND '2015-05-31' THEN f.NetSalesAmount END), 0), 1) AS crecimiento_pct
FROM WWI_DW.dw.FactSales f
JOIN WWI_DW.dw.DimDate d     ON d.DateKey = f.DateKey
JOIN WWI_DW.dw.DimCustomer c ON c.CustomerKey = f.CustomerKey
WHERE c.CustomerKey <> -1
GROUP BY c.StateProvinceName
HAVING SUM(CASE WHEN d.FullDate BETWEEN '2014-05-31' AND '2015-05-31' THEN f.NetSalesAmount END) > 0
ORDER BY crecimiento_pct ASC;