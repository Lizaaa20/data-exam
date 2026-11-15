USE WWI_Staging;
GO

IF OBJECT_ID('clean.Sales_InvoiceLines') IS NULL
CREATE TABLE clean.Sales_InvoiceLines (
    InvoiceLineID        INT            NOT NULL PRIMARY KEY,
    InvoiceID            INT            NOT NULL,
    StockItemID          INT            NOT NULL,
    CustomerID           INT            NOT NULL,
    SalespersonPersonID  INT            NOT NULL,
    InvoiceDate          DATE           NOT NULL,
    Quantity             INT            NOT NULL,
    UnitPrice            DECIMAL(18,2)  NOT NULL,
    TaxAmount            DECIMAL(18,2)  NOT NULL,
    LineProfit           DECIMAL(18,2)  NOT NULL,
    ExtendedPrice        DECIMAL(18,2)  NOT NULL,
    NetSalesAmount       DECIMAL(18,2)  NOT NULL,   -- Quantity * UnitPrice
    FlagTotalIncoherente BIT            NOT NULL,   -- regla TOTAL_COHERENTE (solo marca)
    _execution_id        BIGINT         NOT NULL
);
GO

CREATE OR ALTER PROCEDURE clean.usp_clean_sales @execution_id BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRAN;

    -- Evaluación: una fila por línea, con la primera regla que incumple (si hay)
    SELECT e.*,
           CASE
             WHEN e.rn > 1                                                   THEN 'LINEA_UNICA'
             WHEN e.Quantity IS NULL OR e.Quantity <= 0                      THEN 'CANTIDAD_POSITIVA'
             WHEN e.UnitPrice IS NULL OR e.UnitPrice < 0                     THEN 'PRECIO_NO_NEGATIVO'
             WHEN e.InvoiceDate IS NULL OR e.InvoiceDate < '2013-01-01'
                  OR e.InvoiceDate > CAST(SYSDATETIME() AS DATE)             THEN 'FECHA_VALIDA'
             WHEN NOT EXISTS (SELECT 1 FROM raw.Sales_Customers c
                              WHERE c.CustomerID = e.CustomerID)             THEN 'CLIENTE_EXISTE'
             WHEN NOT EXISTS (SELECT 1 FROM raw.Warehouse_StockItems p
                              WHERE p.StockItemID = e.StockItemID)           THEN 'PRODUCTO_EXISTE'
           END AS failed_rule
    INTO #eval
    FROM (
        SELECT l.InvoiceLineID, l.InvoiceID, l.StockItemID, l.Quantity, l.UnitPrice,
               l.TaxAmount, l.LineProfit, l.ExtendedPrice,
               i.CustomerID, i.InvoiceDate, i.SalespersonPersonID,
               ROW_NUMBER() OVER (PARTITION BY l.InvoiceLineID
                                  ORDER BY l.LastEditedWhen DESC, l._loaded_at DESC) AS rn
        FROM raw.Sales_InvoiceLines l
        LEFT JOIN raw.Sales_Invoices i ON i.InvoiceID = l.InvoiceID
    ) e;

    -- Cuarentena
    INSERT quarantine.rejected_rows (execution_id, source_object, source_key, rule_name, detail, raw_payload)
    SELECT @execution_id, 'Sales.InvoiceLines', CAST(InvoiceLineID AS NVARCHAR(100)), failed_rule,
           CONCAT('Quantity=', Quantity, '; UnitPrice=', UnitPrice, '; InvoiceDate=', InvoiceDate,
                  '; CustomerID=', CustomerID, '; StockItemID=', StockItemID),
           CONCAT('InvoiceLineID=', InvoiceLineID, '; InvoiceID=', InvoiceID)
    FROM #eval
    WHERE failed_rule IS NOT NULL;

    -- Datos válidos (se reconstruye completo en cada ejecución: idempotente)
    DELETE FROM clean.Sales_InvoiceLines;

    INSERT clean.Sales_InvoiceLines
        (InvoiceLineID, InvoiceID, StockItemID, CustomerID, SalespersonPersonID, InvoiceDate,
         Quantity, UnitPrice, TaxAmount, LineProfit, ExtendedPrice, NetSalesAmount,
         FlagTotalIncoherente, _execution_id)
    SELECT InvoiceLineID, InvoiceID, StockItemID, CustomerID, SalespersonPersonID, InvoiceDate,
           Quantity, UnitPrice, TaxAmount, LineProfit, ExtendedPrice, Quantity * UnitPrice,
           CASE WHEN ABS(ExtendedPrice - (Quantity * UnitPrice + TaxAmount)) > 0.01 THEN 1 ELSE 0 END,
           @execution_id
    FROM #eval
    WHERE failed_rule IS NULL;

    COMMIT;
END;
GO

GRANT EXECUTE ON SCHEMA::clean TO etl_writer;
GO



USE WWI_Staging;
SELECT FlagTotalIncoherente, COUNT(*) AS lineas
FROM clean.Sales_InvoiceLines
GROUP BY FlagTotalIncoherente;