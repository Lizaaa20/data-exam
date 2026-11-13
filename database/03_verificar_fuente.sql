USE master;

SELECT COUNT(*) AS facturas FROM WWI_Source.Sales.Invoices;
SELECT COUNT(*) AS lineas   FROM WWI_Source.Sales.InvoiceLines;
SELECT MIN(InvoiceDate) AS desde, MAX(InvoiceDate) AS hasta FROM WWI_Source.Sales.Invoices;