USE WWI_Staging;
GO

-- Registro de cada ejecución del ETL
IF OBJECT_ID('audit.etl_run') IS NULL
CREATE TABLE audit.etl_run (
    execution_id     BIGINT IDENTITY(1,1) PRIMARY KEY,
    pipeline_name    NVARCHAR(100)  NOT NULL,
    start_time       DATETIME2(3)   NOT NULL DEFAULT SYSDATETIME(),
    end_time         DATETIME2(3)   NULL,
    source_object    NVARCHAR(200)  NULL,
    target_object    NVARCHAR(200)  NULL,
    rows_read        INT            NULL,
    rows_inserted    INT            NULL,
    rows_updated     INT            NULL,
    rows_rejected    INT            NULL,
    status           NVARCHAR(20)   NOT NULL DEFAULT 'RUNNING',  -- RUNNING / SUCCESS / FAILED
    error_detail     NVARCHAR(MAX)  NULL,
    watermark_start  DATETIME2(7)   NULL,
    watermark_end    DATETIME2(7)   NULL
);

-- Último punto procesado por cada pipeline (carga incremental)
IF OBJECT_ID('audit.etl_watermark') IS NULL
CREATE TABLE audit.etl_watermark (
    pipeline_name    NVARCHAR(100) PRIMARY KEY,
    last_watermark   DATETIME2(7)  NOT NULL DEFAULT '1900-01-01',
    updated_at       DATETIME2(3)  NOT NULL DEFAULT SYSDATETIME()
);

-- Catálogo de reglas de calidad
IF OBJECT_ID('audit.quality_rule') IS NULL
CREATE TABLE audit.quality_rule (
    rule_name    NVARCHAR(100) PRIMARY KEY,
    dimension    NVARCHAR(30)  NOT NULL,   -- completitud, unicidad, validez, consistencia, integridad
    description  NVARCHAR(400) NOT NULL,
    action       NVARCHAR(30)  NOT NULL    -- RECHAZAR / CORREGIR / MARCAR
);

-- Registros rechazados
IF OBJECT_ID('quarantine.rejected_rows') IS NULL
CREATE TABLE quarantine.rejected_rows (
    rejected_id    BIGINT IDENTITY(1,1) PRIMARY KEY,
    execution_id   BIGINT         NOT NULL,
    source_object  NVARCHAR(200)  NOT NULL,
    source_key     NVARCHAR(100)  NULL,
    rule_name      NVARCHAR(100)  NOT NULL,
    detail         NVARCHAR(400)  NULL,
    raw_payload    NVARCHAR(MAX)  NULL,
    rejected_at    DATETIME2(3)   NOT NULL DEFAULT SYSDATETIME()
);
GO

-- Pipelines con su watermark inicial
MERGE audit.etl_watermark AS t
USING (VALUES ('invoices'), ('invoice_lines'), ('customers')) AS s(pipeline_name)
   ON t.pipeline_name = s.pipeline_name
WHEN NOT MATCHED THEN INSERT (pipeline_name) VALUES (s.pipeline_name);
GO

-- Reglas de calidad iniciales
MERGE audit.quality_rule AS t
USING (VALUES
 ('CANTIDAD_POSITIVA', 'validez',      'Quantity debe ser mayor que 0',                                 'RECHAZAR'),
 ('PRECIO_NO_NEGATIVO','validez',      'UnitPrice no puede ser negativo',                               'RECHAZAR'),
 ('FECHA_VALIDA',      'validez',      'InvoiceDate dentro del rango 2013-01-01 a hoy',                 'RECHAZAR'),
 ('CLIENTE_EXISTE',    'integridad',   'CustomerID debe existir en Sales.Customers',                    'RECHAZAR'),
 ('PRODUCTO_EXISTE',   'integridad',   'StockItemID debe existir en Warehouse.StockItems',              'RECHAZAR'),
 ('LINEA_UNICA',       'unicidad',     'InvoiceLineID no puede repetirse; se conserva el más reciente', 'RECHAZAR'),
 ('TEXTO_VACIO_A_NULL','completitud',  'Cadenas vacías se convierten a NULL o a categoría explícita',   'CORREGIR'),
 ('TOTAL_COHERENTE',   'consistencia', 'ExtendedPrice = Quantity x UnitPrice + TaxAmount',              'MARCAR')
) AS s(rule_name, dimension, description, action)
   ON t.rule_name = s.rule_name
WHEN NOT MATCHED THEN INSERT (rule_name, dimension, description, action)
     VALUES (s.rule_name, s.dimension, s.description, s.action);
GO

SELECT name, SCHEMA_NAME(schema_id) AS esquema FROM sys.tables
WHERE SCHEMA_NAME(schema_id) IN ('audit','quarantine') ORDER BY esquema, name;
SELECT * FROM audit.quality_rule;