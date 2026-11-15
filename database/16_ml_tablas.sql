USE WWI_DW;
GO
IF OBJECT_ID('dw.ModelRun') IS NULL
CREATE TABLE dw.ModelRun (
    ModelVersion     NVARCHAR(40)   NOT NULL PRIMARY KEY,
    ModelName        NVARCHAR(40)   NOT NULL,
    TrainedAt        DATETIME2(0)   NOT NULL,
    TrainRange       NVARCHAR(40)   NOT NULL,
    TestRange        NVARCHAR(40)   NOT NULL,
    Params           NVARCHAR(MAX)  NULL,
    MaeTest          DECIMAL(18,2)  NOT NULL,
    RmseTest         DECIMAL(18,2)  NOT NULL,
    SmapeTest        DECIMAL(9,2)   NOT NULL,
    BaselineName     NVARCHAR(40)   NOT NULL,
    BaselineMaeTest  DECIMAL(18,2)  NOT NULL
);

IF OBJECT_ID('dw.PredictedSales') IS NULL
CREATE TABLE dw.PredictedSales (
    PredictionKey   BIGINT IDENTITY(1,1) PRIMARY KEY,
    ModelVersion    NVARCHAR(40)  NOT NULL REFERENCES dw.ModelRun(ModelVersion),
    PredictionDate  DATE          NOT NULL,
    Category        NVARCHAR(50)  NOT NULL,
    TargetMonth     CHAR(7)       NOT NULL,   -- yyyy-mm
    HorizonMonths   TINYINT       NOT NULL,
    PredictedSales  DECIMAL(18,2) NOT NULL,
    CONSTRAINT UQ_PredictedSales UNIQUE (ModelVersion, Category, TargetMonth)
);
GO