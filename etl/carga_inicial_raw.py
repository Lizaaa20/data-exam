import os
import sys
import traceback

import pyodbc
from dotenv import load_dotenv

load_dotenv()

HOST, PORT = os.getenv("MSSQL_HOST"), os.getenv("MSSQL_PORT")
PIPELINE = "carga_inicial_raw"
BATCH = 10000

# (esquema, tabla): columnas que se copian (se excluyen columnas sensibles o sin uso)
TABLAS = {
    ("Sales", "Invoices"): ["InvoiceID", "CustomerID", "OrderID", "SalespersonPersonID",
                            "InvoiceDate", "LastEditedWhen"],
    ("Sales", "InvoiceLines"): ["InvoiceLineID", "InvoiceID", "StockItemID", "Quantity", "UnitPrice",
                                "TaxAmount", "LineProfit", "ExtendedPrice", "LastEditedWhen"],
    ("Sales", "Customers"): ["CustomerID", "CustomerName", "CustomerCategoryID", "BuyingGroupID",
                             "DeliveryCityID", "ValidFrom", "ValidTo"],
    ("Sales", "Customers_Archive"): ["CustomerID", "CustomerName", "CustomerCategoryID", "BuyingGroupID",
                                     "DeliveryCityID", "ValidFrom", "ValidTo"],
    ("Sales", "CustomerCategories"): ["CustomerCategoryID", "CustomerCategoryName"],
    ("Sales", "BuyingGroups"): ["BuyingGroupID", "BuyingGroupName"],
    ("Warehouse", "StockItems"): ["StockItemID", "StockItemName", "Brand", "Size", "ColorID"],
    ("Warehouse", "Colors"): ["ColorID", "ColorName"],
    ("Warehouse", "StockGroups"): ["StockGroupID", "StockGroupName"],
    ("Warehouse", "StockItemStockGroups"): ["StockItemStockGroupID", "StockItemID", "StockGroupID"],
    ("Application", "People"): ["PersonID", "FullName"],
    ("Application", "Cities"): ["CityID", "CityName", "StateProvinceID"],
    ("Application", "StateProvinces"): ["StateProvinceID", "StateProvinceName", "CountryID"],
    ("Application", "Countries"): ["CountryID", "CountryName", "Region"],
}


def conectar(user, pwd, db):
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={HOST},{PORT};DATABASE={db};UID={user};PWD={pwd};"
        "TrustServerCertificate=yes;"
    )


def tipo_sql(dt, clen, prec, scale, dprec):
    if dt in ("varchar", "nvarchar", "char", "nchar", "varbinary", "binary"):
        return f"{dt}({'MAX' if clen == -1 else clen})"
    if dt in ("decimal", "numeric"):
        return f"{dt}({prec},{scale})"
    if dt in ("datetime2", "datetimeoffset", "time"):
        return f"{dt}({dprec})"
    return dt


def ddl_raw(src_cur, esquema, tabla, columnas):
    src_cur.execute(
        "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, "
        "NUMERIC_SCALE, DATETIME_PRECISION FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?", esquema, tabla)
    info = {r[0]: r[1:] for r in src_cur.fetchall()}
    faltan = [c for c in columnas if c not in info]
    if faltan:
        raise RuntimeError(f"{esquema}.{tabla}: columnas inexistentes en la fuente: {faltan}")
    defs = [f"[{c}] {tipo_sql(*info[c])} NULL" for c in columnas]
    defs += ["[_execution_id] BIGINT NOT NULL",
             "[_loaded_at] DATETIME2(3) NOT NULL DEFAULT SYSDATETIME()"]
    return defs


def abrir_run(dst, origen, destino):
    cur = dst.cursor()
    cur.execute("INSERT audit.etl_run (pipeline_name, source_object, target_object) "
                "OUTPUT INSERTED.execution_id VALUES (?, ?, ?)", PIPELINE, origen, destino)
    exec_id = cur.fetchone()[0]
    dst.commit()
    return exec_id


def cerrar_run(dst, exec_id, leidas, insertadas, estado, error=None):
    dst.cursor().execute(
        "UPDATE audit.etl_run SET end_time = SYSDATETIME(), rows_read = ?, rows_inserted = ?, "
        "rows_rejected = 0, status = ?, error_detail = ? WHERE execution_id = ?",
        leidas, insertadas, estado, error, exec_id)
    dst.commit()


def cargar(src, dst, esquema, tabla, columnas):
    origen, raw = f"{esquema}.{tabla}", f"raw.{esquema}_{tabla}"
    exec_id = abrir_run(dst, origen, raw)
    leidas = insertadas = 0
    try:
        s, d = src.cursor(), dst.cursor()
        defs = ddl_raw(s, esquema, tabla, columnas)
        d.execute(f"DROP TABLE IF EXISTS {raw}")
        d.execute(f"CREATE TABLE {raw} ({', '.join(defs)})")

        cols = ", ".join(f"[{c}]" for c in columnas)
        ins = (f"INSERT INTO {raw} ({cols}, [_execution_id]) "
               f"VALUES ({', '.join('?' * (len(columnas) + 1))})")
        d.fast_executemany = True
        s.execute(f"SELECT {cols} FROM [{esquema}].[{tabla}]")
        while True:
            filas = s.fetchmany(BATCH)
            if not filas:
                break
            leidas += len(filas)
            d.executemany(ins, [tuple(f) + (exec_id,) for f in filas])
            insertadas += len(filas)

        d.execute(f"SELECT COUNT(*) FROM {raw}")
        en_raw = d.fetchone()[0]
        if en_raw != leidas:
            raise RuntimeError(f"Conteo no coincide: leidas={leidas}, en raw={en_raw}")
        dst.commit()
        cerrar_run(dst, exec_id, leidas, insertadas, "SUCCESS")
        print(f"OK  {origen:<35} {insertadas:>8} filas")
        return True
    except Exception as e:
        dst.rollback()
        cerrar_run(dst, exec_id, leidas, 0, "FAILED", str(e)[:4000])
        print(f"ERR {origen}: {e}")
        traceback.print_exc()
        return False


def main():
    src = conectar(os.getenv("MSSQL_READER_USER"), os.getenv("MSSQL_READER_PASSWORD"), "WWI_Source")
    dst = conectar(os.getenv("MSSQL_WRITER_USER"), os.getenv("MSSQL_WRITER_PASSWORD"), "WWI_Staging")

    resultados = [cargar(src, dst, e, t, cols) for (e, t), cols in TABLAS.items()]

    if all(resultados):
        # Watermark: solo se actualiza si TODA la carga terminó bien
        c = dst.cursor()
        c.execute("UPDATE audit.etl_watermark SET last_watermark = "
                  "(SELECT MAX(LastEditedWhen) FROM raw.Sales_Invoices), updated_at = SYSDATETIME() "
                  "WHERE pipeline_name = 'invoices'")
        c.execute("UPDATE audit.etl_watermark SET last_watermark = "
                  "(SELECT MAX(LastEditedWhen) FROM raw.Sales_InvoiceLines), updated_at = SYSDATETIME() "
                  "WHERE pipeline_name = 'invoice_lines'")
        c.execute("UPDATE audit.etl_watermark SET last_watermark = "
                  "(SELECT MAX(ValidFrom) FROM raw.Sales_Customers), updated_at = SYSDATETIME() "
                  "WHERE pipeline_name = 'customers'")
        dst.commit()
        print("Carga inicial completa. Watermarks actualizados.")
    else:
        print("La carga tuvo errores. Watermarks SIN actualizar. Revisa audit.etl_run.")
        sys.exit(1)


if __name__ == "__main__":
    main()