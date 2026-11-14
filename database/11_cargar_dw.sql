USE WWI_DW;
GO
CREATE OR ALTER PROCEDURE dw.usp_load_dw
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    BEGIN TRAN;

    DECLARE @a TABLE (tabla SYSNAME, accion NVARCHAR(10));

    -- DimProduct (Tipo 1)
    MERGE dw.DimProduct AS t
    USING WWI_Staging.ready.vDimProduct AS s ON t.StockItemID = s.StockItemID
    WHEN MATCHED AND (t.StockItemName <> s.StockItemName OR t.Brand <> s.Brand OR t.ColorName <> s.ColorName
                      OR t.Size <> s.Size OR t.PrimaryCategory <> s.PrimaryCategory)
        THEN UPDATE SET StockItemName = s.StockItemName, Brand = s.Brand, ColorName = s.ColorName,
                        Size = s.Size, PrimaryCategory = s.PrimaryCategory
    WHEN NOT MATCHED BY TARGET
        THEN INSERT (StockItemID, StockItemName, Brand, ColorName, Size, PrimaryCategory)
             VALUES (s.StockItemID, s.StockItemName, s.Brand, s.ColorName, s.Size, s.PrimaryCategory)
    OUTPUT 'DimProduct', $action INTO @a;

    -- DimSalesperson (Tipo 1)
    MERGE dw.DimSalesperson AS t
    USING WWI_Staging.ready.vDimSalesperson AS s ON t.PersonID = s.PersonID
    WHEN MATCHED AND t.FullName <> s.FullName
        THEN UPDATE SET FullName = s.FullName
    WHEN NOT MATCHED BY TARGET
        THEN INSERT (PersonID, FullName) VALUES (s.PersonID, s.FullName)
    OUTPUT 'DimSalesperson', $action INTO @a;

    -- DimCustomer (SCD Tipo 2: una fila por versión)
    MERGE dw.DimCustomer AS t
    USING WWI_Staging.ready.vDimCustomer AS s
       ON t.CustomerID = s.CustomerID AND t.ValidFrom = s.ValidFrom
    WHEN MATCHED AND (t.ValidTo <> s.ValidTo OR t.IsCurrent <> s.IsCurrent OR t.CustomerName <> s.CustomerName
                      OR t.CustomerCategory <> s.CustomerCategory OR t.BuyingGroup <> s.BuyingGroup
                      OR t.CityName <> s.CityName OR t.StateProvinceName <> s.StateProvinceName
                      OR t.CountryName <> s.CountryName OR t.Region <> s.Region)
        THEN UPDATE SET ValidTo = s.ValidTo, IsCurrent = s.IsCurrent, CustomerName = s.CustomerName,
                        CustomerCategory = s.CustomerCategory, BuyingGroup = s.BuyingGroup,
                        CityName = s.CityName, StateProvinceName = s.StateProvinceName,
                        CountryName = s.CountryName, Region = s.Region
    WHEN NOT MATCHED BY TARGET
        THEN INSERT (CustomerID, CustomerName, CustomerCategory, BuyingGroup, CityName, StateProvinceName,
                     CountryName, Region, ValidFrom, ValidTo, IsCurrent)
             VALUES (s.CustomerID, s.CustomerName, s.CustomerCategory, s.BuyingGroup, s.CityName,
                     s.StateProvinceName, s.CountryName, s.Region, s.ValidFrom, s.ValidTo, s.IsCurrent)
    OUTPUT 'DimCustomer', $action INTO @a;

    -- FactSales (upsert por InvoiceLineID; claves resueltas contra las dimensiones)
    ;WITH src AS (
        SELECT l.InvoiceLineID, l.InvoiceID,
               YEAR(l.InvoiceDate) * 10000 + MONTH(l.InvoiceDate) * 100 + DAY(l.InvoiceDate) AS DateKey,
               COALESCE(c.CustomerKey, -1)    AS CustomerKey,
               COALESCE(p.ProductKey, -1)     AS ProductKey,
               COALESCE(sp.SalespersonKey, -1) AS SalespersonKey,
               l.Quantity, l.UnitPrice, l.NetSalesAmount, l.TaxAmount, l.ExtendedPrice, l.LineProfit
        FROM WWI_Staging.clean.Sales_InvoiceLines l
        OUTER APPLY (SELECT TOP 1 dc.CustomerKey
                     FROM dw.DimCustomer dc
                     WHERE dc.CustomerID = l.CustomerID
                     ORDER BY CASE WHEN l.InvoiceDate >= dc.ValidFrom AND l.InvoiceDate < dc.ValidTo
                                   THEN 0 ELSE 1 END, dc.ValidFrom) c
        LEFT JOIN dw.DimProduct     p  ON p.StockItemID = l.StockItemID
        LEFT JOIN dw.DimSalesperson sp ON sp.PersonID   = l.SalespersonPersonID
    )
    MERGE dw.FactSales AS t
    USING src AS s ON t.InvoiceLineID = s.InvoiceLineID
    WHEN MATCHED AND (t.DateKey <> s.DateKey OR t.CustomerKey <> s.CustomerKey OR t.ProductKey <> s.ProductKey
                      OR t.SalespersonKey <> s.SalespersonKey OR t.Quantity <> s.Quantity
                      OR t.UnitPrice <> s.UnitPrice OR t.NetSalesAmount <> s.NetSalesAmount
                      OR t.TaxAmount <> s.TaxAmount OR t.ExtendedPrice <> s.ExtendedPrice
                      OR t.LineProfit <> s.LineProfit)
        THEN UPDATE SET DateKey = s.DateKey, CustomerKey = s.CustomerKey, ProductKey = s.ProductKey,
                        SalespersonKey = s.SalespersonKey, Quantity = s.Quantity, UnitPrice = s.UnitPrice,
                        NetSalesAmount = s.NetSalesAmount, TaxAmount = s.TaxAmount,
                        ExtendedPrice = s.ExtendedPrice, LineProfit = s.LineProfit
    WHEN NOT MATCHED BY TARGET
        THEN INSERT (DateKey, CustomerKey, ProductKey, SalespersonKey, InvoiceID, InvoiceLineID, Quantity,
                     UnitPrice, NetSalesAmount, TaxAmount, ExtendedPrice, LineProfit)
             VALUES (s.DateKey, s.CustomerKey, s.ProductKey, s.SalespersonKey, s.InvoiceID, s.InvoiceLineID,
                     s.Quantity, s.UnitPrice, s.NetSalesAmount, s.TaxAmount, s.ExtendedPrice, s.LineProfit)
    OUTPUT 'FactSales', $action INTO @a;

    COMMIT;

    SELECT tabla, accion, COUNT(*) AS filas FROM @a GROUP BY tabla, accion;
END;
GO

GRANT EXECUTE ON SCHEMA::dw TO etl_writer;
GO