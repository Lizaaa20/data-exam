USE WWI_Staging;
DELETE FROM raw.Sales_InvoiceLines WHERE _execution_id = -1;
DELETE FROM raw.Sales_Invoices      WHERE _execution_id = -1;
SELECT COUNT(*) AS lineas_en_raw FROM raw.Sales_InvoiceLines;   -- esperado: 228265