SELECT 'Fuente' AS capa, COUNT(*) AS lineas, SUM(Quantity * UnitPrice) AS ventas_netas, SUM(LineProfit) AS utilidad
FROM WWI_Source.Sales.InvoiceLines
UNION ALL
SELECT 'Staging clean', COUNT(*), SUM(NetSalesAmount), SUM(LineProfit)
FROM WWI_Staging.clean.Sales_InvoiceLines
UNION ALL
SELECT 'Data Warehouse', COUNT(*), SUM(NetSalesAmount), SUM(LineProfit)
FROM WWI_DW.dw.FactSales;

-- Hechos sin dimensión real (deben ser 0)
SELECT SUM(CASE WHEN CustomerKey    = -1 THEN 1 ELSE 0 END) AS sin_cliente,
       SUM(CASE WHEN ProductKey     = -1 THEN 1 ELSE 0 END) AS sin_producto,
       SUM(CASE WHEN SalespersonKey = -1 THEN 1 ELSE 0 END) AS sin_vendedor
FROM WWI_DW.dw.FactSales;

-- Ventas por año: fuente vs DW
SELECT YEAR(i.InvoiceDate) AS anio, SUM(l.Quantity * l.UnitPrice) AS fuente
FROM WWI_Source.Sales.InvoiceLines l JOIN WWI_Source.Sales.Invoices i ON i.InvoiceID = l.InvoiceID
GROUP BY YEAR(i.InvoiceDate) ORDER BY anio;

SELECT d.YearNum AS anio, SUM(f.NetSalesAmount) AS dw
FROM WWI_DW.dw.FactSales f JOIN WWI_DW.dw.DimDate d ON d.DateKey = f.DateKey
GROUP BY d.YearNum ORDER BY anio;