USE WWI_Staging;
GO

-- Clientes: todas las versiones (SCD Tipo 2) a partir de Customers + Customers_Archive
CREATE OR ALTER VIEW ready.vDimCustomer AS
WITH versiones AS (
    SELECT CustomerID, CustomerName, CustomerCategoryID, BuyingGroupID, DeliveryCityID, ValidFrom
    FROM raw.Sales_Customers
    UNION ALL
    SELECT CustomerID, CustomerName, CustomerCategoryID, BuyingGroupID, DeliveryCityID, ValidFrom
    FROM raw.Sales_Customers_Archive
),
dedup AS (   -- varias ediciones el mismo día: se conserva la última
    SELECT *, ROW_NUMBER() OVER (PARTITION BY CustomerID, CAST(ValidFrom AS DATE)
                                 ORDER BY ValidFrom DESC) AS rn
    FROM versiones
),
v AS (
    SELECT *, CAST(ValidFrom AS DATE) AS vf,
           LEAD(CAST(ValidFrom AS DATE)) OVER (PARTITION BY CustomerID ORDER BY ValidFrom) AS next_vf
    FROM dedup
    WHERE rn = 1
)
SELECT v.CustomerID,
       v.CustomerName,
       COALESCE(cc.CustomerCategoryName, N'Sin categoría') AS CustomerCategory,
       COALESCE(bg.BuyingGroupName,      N'Sin grupo')     AS BuyingGroup,
       COALESCE(ci.CityName,             N'Desconocido')   AS CityName,
       COALESCE(sp.StateProvinceName,    N'Desconocido')   AS StateProvinceName,
       COALESCE(co.CountryName,          N'Desconocido')   AS CountryName,
       COALESCE(co.Region,               N'Desconocido')   AS Region,
       v.vf                                   AS ValidFrom,
       COALESCE(v.next_vf, '9999-12-31')      AS ValidTo,
       CASE WHEN v.next_vf IS NULL THEN 1 ELSE 0 END AS IsCurrent
FROM v
LEFT JOIN raw.Sales_CustomerCategories  cc ON cc.CustomerCategoryID = v.CustomerCategoryID
LEFT JOIN raw.Sales_BuyingGroups        bg ON bg.BuyingGroupID      = v.BuyingGroupID
LEFT JOIN raw.Application_Cities        ci ON ci.CityID             = v.DeliveryCityID
LEFT JOIN raw.Application_StateProvinces sp ON sp.StateProvinceID   = ci.StateProvinceID
LEFT JOIN raw.Application_Countries     co ON co.CountryID          = sp.CountryID;
GO

-- Productos: categoría principal = grupo con mayor StockGroupID
CREATE OR ALTER VIEW ready.vDimProduct AS
SELECT p.StockItemID,
       p.StockItemName,
       COALESCE(NULLIF(LTRIM(RTRIM(p.Brand)), N''), N'Sin marca') AS Brand,
       COALESCE(col.ColorName, N'Sin color')                      AS ColorName,
       COALESCE(NULLIF(LTRIM(RTRIM(p.Size)),  N''), N'Sin talla') AS Size,
       COALESCE(g.StockGroupName, N'Sin categoría')               AS PrimaryCategory
FROM raw.Warehouse_StockItems p
LEFT JOIN raw.Warehouse_Colors col ON col.ColorID = p.ColorID
LEFT JOIN (SELECT StockItemID, MAX(StockGroupID) AS StockGroupID
           FROM raw.Warehouse_StockItemStockGroups
           GROUP BY StockItemID) pg ON pg.StockItemID = p.StockItemID
LEFT JOIN raw.Warehouse_StockGroups g ON g.StockGroupID = pg.StockGroupID;
GO

-- Vendedores: solo los que aparecen en ventas válidas
CREATE OR ALTER VIEW ready.vDimSalesperson AS
SELECT pe.PersonID, pe.FullName
FROM raw.Application_People pe
WHERE EXISTS (SELECT 1 FROM clean.Sales_InvoiceLines l WHERE l.SalespersonPersonID = pe.PersonID);
GO

USE WWI_Staging;

-- Clientes: 663 vigentes y las versiones históricas
SELECT COUNT(*) AS versiones,
       SUM(IsCurrent) AS vigentes,
       COUNT(DISTINCT CustomerID) AS clientes
FROM ready.vDimCustomer;

-- Productos: 227, y la distribución debe coincidir con la regla elegida
SELECT PrimaryCategory, COUNT(*) AS productos
FROM ready.vDimProduct GROUP BY PrimaryCategory ORDER BY productos DESC;

-- Vendedores
SELECT COUNT(*) AS vendedores FROM ready.vDimSalesperson;