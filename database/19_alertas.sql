USE WWI_DW;
GO
IF OBJECT_ID('dw.Alert') IS NULL
CREATE TABLE dw.Alert (
    AlertId           BIGINT IDENTITY(1,1) PRIMARY KEY,
    CreatedAt         DATETIME2(0)  NOT NULL DEFAULT SYSDATETIME(),
    UpdatedAt         DATETIME2(0)  NULL,
    AlertType         NVARCHAR(30)  NOT NULL,
    Severity          NVARCHAR(10)  NOT NULL,
    Indicator         NVARCHAR(60)  NOT NULL,
    Entity            NVARCHAR(100) NOT NULL,
    ObservedValue     DECIMAL(18,2) NOT NULL,
    ReferenceValue    DECIMAL(18,2) NOT NULL,
    ChangePct         DECIMAL(9,2)  NOT NULL,
    ThresholdPct      DECIMAL(9,2)  NOT NULL,
    ReferencePeriod   NVARCHAR(60)  NOT NULL,
    Source            NVARCHAR(20)  NOT NULL,
    ModelVersion      NVARCHAR(40)  NULL,
    Explanation       NVARCHAR(500) NOT NULL,
    RecommendedAction NVARCHAR(300) NULL,
    Status            NVARCHAR(12)  NOT NULL DEFAULT 'NUEVA',
    DedupKey          NVARCHAR(200) NOT NULL,
    CONSTRAINT UQ_Alert_Dedup UNIQUE (DedupKey),
    CONSTRAINT CK_Alert_Status CHECK (Status IN ('NUEVA','ATENDIDA','DESCARTADA','RESUELTA'))
);
GO
IF OBJECT_ID('dw.AlertDelivery') IS NULL
CREATE TABLE dw.AlertDelivery (
    DeliveryId    BIGINT IDENTITY(1,1) PRIMARY KEY,
    AlertId       BIGINT       NOT NULL REFERENCES dw.Alert(AlertId),
    Channel       NVARCHAR(20) NOT NULL,
    Status        NVARCHAR(10) NOT NULL DEFAULT 'PENDIENTE',
    Attempts      INT          NOT NULL DEFAULT 0,
    LastError     NVARCHAR(400) NULL,
    LastAttemptAt DATETIME2(0) NULL,
    DeliveredAt   DATETIME2(0) NULL,
    CONSTRAINT UQ_AlertDelivery UNIQUE (AlertId, Channel)
);
GO
CREATE OR ALTER PROCEDURE dw.usp_set_alert_status @AlertId BIGINT, @Status NVARCHAR(12)
AS
BEGIN
    SET NOCOUNT ON;
    IF @Status NOT IN ('NUEVA','ATENDIDA','DESCARTADA','RESUELTA')
        THROW 50001, 'Estado no válido', 1;
    UPDATE dw.Alert SET Status = @Status, UpdatedAt = SYSDATETIME() WHERE AlertId = @AlertId;
    SELECT @@ROWCOUNT AS filas;
END;
GO
GRANT EXECUTE ON dw.usp_set_alert_status TO api_reader;
GO