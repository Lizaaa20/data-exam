import os
import sys
from datetime import timedelta

import carga_inicial_raw as ci
from carga_inicial_raw import TABLAS, cargar, conectar
from dotenv import load_dotenv

load_dotenv()
OVERLAP_HORAS = int(os.getenv("INCREMENTAL_OVERLAP_HORAS", "24"))
BATCH = 10000

INCREMENTALES = {
    "invoices": ("Sales", "Invoices", "InvoiceID"),
    "invoice_lines": ("Sales", "InvoiceLines", "InvoiceLineID"),
}


def incremental(src, dst, pipeline, esquema, tabla, clave):
    s, d = src.cursor(), dst.cursor()
    raw = f"raw.{esquema}_{tabla}"
    cols = TABLAS[(esquema, tabla)]
    cols_sql = ", ".join(f"[{c}]" for c in cols)

    d.execute("SELECT last_watermark FROM audit.etl_watermark WHERE pipeline_name = ?", pipeline)
    wm = d.fetchone()[0]
    desde = wm - timedelta(hours=OVERLAP_HORAS)

    d.execute("INSERT audit.etl_run (pipeline_name, source_object, target_object, watermark_start) "
              "OUTPUT INSERTED.execution_id VALUES (?, ?, ?, ?)",
              f"incremental_{pipeline}", f"{esquema}.{tabla}", raw, desde)
    exec_id = d.fetchone()[0]
    dst.commit()

    try:
        # La conexión se reutiliza entre tablas: se borra la temporal de la tabla anterior
        d.execute("DROP TABLE IF EXISTS #inc")
        d.execute(f"SELECT TOP 0 {cols_sql} INTO #inc FROM {raw}")
        d.fast_executemany = True
        ins = f"INSERT INTO #inc ({cols_sql}) VALUES ({', '.join('?' * len(cols))})"
        s.execute(f"SELECT {cols_sql} FROM [{esquema}].[{tabla}] WHERE LastEditedWhen > ?", desde)
        leidas = 0
        while True:
            filas = s.fetchmany(BATCH)
            if not filas:
                break
            leidas += len(filas)
            d.executemany(ins, [tuple(f) for f in filas])

        sets = ", ".join(f"t.[{c}] = s.[{c}]" for c in cols if c != clave)
        valores = ", ".join(f"s.[{c}]" for c in cols)
        sql = (
            "SET NOCOUNT ON; "
            "DECLARE @a TABLE (accion NVARCHAR(10)); "
            f"MERGE {raw} AS t USING #inc AS s ON t.[{clave}] = s.[{clave}] "
            "WHEN MATCHED AND s.LastEditedWhen > t.LastEditedWhen THEN "
            f"UPDATE SET {sets}, t._execution_id = ?, t._loaded_at = SYSDATETIME() "
            "WHEN NOT MATCHED BY TARGET THEN "
            f"INSERT ({cols_sql}, _execution_id) VALUES ({valores}, ?) "
            "OUTPUT $action INTO @a; "
            "SELECT accion, COUNT(*) FROM @a GROUP BY accion;"
        )
        d.execute(sql, exec_id, exec_id)
        res = {r[0]: r[1] for r in d.fetchall()}
        ins_n, upd_n = res.get("INSERT", 0), res.get("UPDATE", 0)

        d.execute("SELECT MAX(LastEditedWhen) FROM #inc")
        nuevo_wm = d.fetchone()[0] or wm
        nuevo_wm = max(nuevo_wm, wm)

        d.execute("UPDATE audit.etl_run SET end_time = SYSDATETIME(), rows_read = ?, rows_inserted = ?, "
                  "rows_updated = ?, rows_rejected = 0, status = 'SUCCESS', watermark_end = ? "
                  "WHERE execution_id = ?", leidas, ins_n, upd_n, nuevo_wm, exec_id)
        # El watermark solo avanza si TODO lo anterior terminó bien (misma transacción)
        d.execute("UPDATE audit.etl_watermark SET last_watermark = ?, updated_at = SYSDATETIME() "
                  "WHERE pipeline_name = ?", nuevo_wm, pipeline)
        dst.commit()
        print(f"OK  {esquema}.{tabla:<14} leidas={leidas:>6}  nuevas={ins_n:>5}  modificadas={upd_n:>5}  "
              f"ventana desde {desde:%Y-%m-%d %H:%M}")
        return True
    except Exception as e:
        dst.rollback()
        d.execute("UPDATE audit.etl_run SET end_time = SYSDATETIME(), status = 'FAILED', error_detail = ? "
                  "WHERE execution_id = ?", str(e)[:4000], exec_id)
        dst.commit()
        print(f"ERR {esquema}.{tabla}: {e}")
        return False


def main():
    src = conectar(os.getenv("MSSQL_READER_USER"), os.getenv("MSSQL_READER_PASSWORD"), "WWI_Source")
    dst = conectar(os.getenv("MSSQL_WRITER_USER"), os.getenv("MSSQL_WRITER_PASSWORD"), "WWI_Staging")

    ok = all([incremental(src, dst, p, e, t, k) for p, (e, t, k) in INCREMENTALES.items()])

    # Catálogos pequeños: recarga completa (se registra con otro nombre de pipeline)
    ci.PIPELINE = "carga_catalogos"
    for (e, t), cols in TABLAS.items():
        if t not in ("Invoices", "InvoiceLines"):
            ok = cargar(src, dst, e, t, cols) and ok

    if ok:
        c = dst.cursor()
        c.execute("UPDATE audit.etl_watermark SET last_watermark = "
                  "(SELECT MAX(ValidFrom) FROM raw.Sales_Customers), updated_at = SYSDATETIME() "
                  "WHERE pipeline_name = 'customers'")
        dst.commit()
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()