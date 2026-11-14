import os
from datetime import datetime

import pandas as pd
import pyodbc
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

load_dotenv()

HOST = os.getenv("MSSQL_HOST")
PORT = os.getenv("MSSQL_PORT")
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
DOC_DIR = "documentation"

# (esquema, tabla, [claves a revisar]) -> cada lista de claves se revisa por duplicados
TABLAS = [
    ("Sales", "Invoices", [["InvoiceID"]]),
    ("Sales", "InvoiceLines", [["InvoiceLineID"]]),
    ("Sales", "Orders", [["OrderID"]]),
    ("Sales", "Customers", [["CustomerID"], ["CustomerName"]]),
    ("Warehouse", "StockItems", [["StockItemID"], ["StockItemName"]]),
    ("Warehouse", "StockGroups", [["StockGroupID"]]),
    ("Warehouse", "StockItemStockGroups", [["StockItemStockGroupID"]]),
    ("Application", "People", [["PersonID"]]),
    ("Application", "Cities", [["CityID"]]),
    ("Application", "StateProvinces", [["StateProvinceID"]]),
    ("Application", "Countries", [["CountryID"]]),
]

TEXTO = {"char", "varchar", "nchar", "nvarchar"}
SIN_DISTINCT = {"xml", "geography", "geometry", "hierarchyid", "image", "text", "ntext", "varbinary", "binary"}
SIN_MINMAX = SIN_DISTINCT | {"uniqueidentifier"}


def conectar(user, pwd, db):
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={HOST},{PORT};DATABASE={db};UID={user};PWD={pwd};"
        "TrustServerCertificate=yes;"
    )


def texto(v):
    return None if v is None else str(v)


def perfilar_columna(cur, esquema, tabla, col, tipo):
    c = f"[{col}]"
    exprs = ["COUNT(*)", f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END)"]
    nombres = ["filas", "nulos"]

    if tipo not in SIN_DISTINCT:
        exprs.append(f"COUNT(DISTINCT {c})")
        nombres.append("distintos")
    if tipo not in SIN_MINMAX:
        base = f"CAST({c} AS INT)" if tipo == "bit" else c
        exprs += [f"MIN({base})", f"MAX({base})"]
        nombres += ["minimo", "maximo"]
    if tipo in TEXTO:
        exprs.append(f"SUM(CASE WHEN LTRIM(RTRIM({c})) = '' THEN 1 ELSE 0 END)")
        exprs.append(f"SUM(CASE WHEN {c} <> LTRIM(RTRIM({c})) THEN 1 ELSE 0 END)")
        nombres += ["vacios", "con_espacios_extremos"]

    cur.execute(f"SELECT {', '.join(exprs)} FROM [{esquema}].[{tabla}]")
    fila = dict(zip(nombres, cur.fetchone()))
    filas = fila["filas"] or 0
    nulos = fila["nulos"] or 0
    return {
        "run_id": RUN_ID,
        "esquema": esquema,
        "tabla": tabla,
        "columna": col,
        "tipo": tipo,
        "filas": filas,
        "nulos": nulos,
        "pct_nulos": round(nulos * 100.0 / filas, 2) if filas else 0,
        "distintos": fila.get("distintos"),
        "minimo": texto(fila.get("minimo")),
        "maximo": texto(fila.get("maximo")),
        "vacios": fila.get("vacios"),
        "con_espacios_extremos": fila.get("con_espacios_extremos"),
    }


def duplicados(cur, esquema, tabla, claves):
    cols = ", ".join(f"[{k}]" for k in claves)
    cur.execute(
        f"SELECT COUNT(*), ISNULL(SUM(n - 1), 0) FROM ("
        f"SELECT COUNT(*) AS n FROM [{esquema}].[{tabla}] GROUP BY {cols} HAVING COUNT(*) > 1) d"
    )
    grupos, sobrantes = cur.fetchone()
    return {
        "run_id": RUN_ID,
        "esquema": esquema,
        "tabla": tabla,
        "clave": ", ".join(claves),
        "grupos_duplicados": grupos,
        "filas_sobrantes": int(sobrantes),
    }


def main():
    conn = conectar(os.getenv("MSSQL_READER_USER"), os.getenv("MSSQL_READER_PASSWORD"), "WWI_Source")
    cur = conn.cursor()
    perfil, dups = [], []

    for esquema, tabla, claves in TABLAS:
        cur.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            esquema, tabla,
        )
        columnas = cur.fetchall()
        print(f"Perfilando {esquema}.{tabla} ({len(columnas)} columnas)")
        for col, tipo in columnas:
            perfil.append(perfilar_columna(cur, esquema, tabla, col, tipo))
        for k in claves:
            dups.append(duplicados(cur, esquema, tabla, k))
    conn.close()

    df_perfil, df_dups = pd.DataFrame(perfil), pd.DataFrame(dups)

    os.makedirs(DOC_DIR, exist_ok=True)
    df_perfil.to_csv(f"{DOC_DIR}/perfil_columnas.csv", index=False, encoding="utf-8-sig")
    df_dups.to_csv(f"{DOC_DIR}/perfil_duplicados.csv", index=False, encoding="utf-8-sig")
    print(f"CSV guardados en {DOC_DIR}/")

    try:
        url = URL.create(
            "mssql+pyodbc",
            username=os.getenv("MSSQL_WRITER_USER"),
            password=os.getenv("MSSQL_WRITER_PASSWORD"),
            host=HOST, port=int(PORT), database="WWI_Staging",
            query={"driver": "ODBC Driver 18 for SQL Server", "TrustServerCertificate": "yes"},
        )
        eng = create_engine(url)
        df_perfil.to_sql("perfil_columnas", eng, schema="audit", if_exists="append", index=False)
        df_dups.to_sql("perfil_duplicados", eng, schema="audit", if_exists="append", index=False)
        print("Resultados cargados en WWI_Staging.audit")
    except Exception as e:
        print("No se pudo escribir en WWI_Staging.audit:", e)

    print(f"Listo. run_id={RUN_ID}, columnas={len(df_perfil)}")


if __name__ == "__main__":
    main()