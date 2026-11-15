import os
import sys

import pyodbc
from dotenv import load_dotenv

load_dotenv()
PIPELINE = "load_dw"


def conectar(db):
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.getenv('MSSQL_HOST')},{os.getenv('MSSQL_PORT')};DATABASE={db};"
        f"UID={os.getenv('MSSQL_WRITER_USER')};PWD={os.getenv('MSSQL_WRITER_PASSWORD')};"
        "TrustServerCertificate=yes;"
    )


stg, dw = conectar("WWI_Staging"), conectar("WWI_DW")
s, d = stg.cursor(), dw.cursor()

s.execute("INSERT audit.etl_run (pipeline_name, source_object, target_object) "
          "OUTPUT INSERTED.execution_id VALUES (?, 'WWI_Staging.clean / ready', 'WWI_DW.dw')", PIPELINE)
exec_id = s.fetchone()[0]
stg.commit()

try:
    s.execute("SELECT COUNT(*) FROM clean.Sales_InvoiceLines")
    leidas = s.fetchone()[0]

    d.execute("EXEC dw.usp_load_dw")
    resultado = d.fetchall()
    dw.commit()

    insertadas = sum(r.filas for r in resultado if r.accion == "INSERT")
    actualizadas = sum(r.filas for r in resultado if r.accion == "UPDATE")
    for r in sorted(resultado, key=lambda x: (x.tabla, x.accion)):
        print(f"{r.tabla:<16} {r.accion:<7} {r.filas:>8}")

    s.execute("UPDATE audit.etl_run SET end_time = SYSDATETIME(), rows_read = ?, rows_inserted = ?, "
              "rows_updated = ?, rows_rejected = 0, status = 'SUCCESS' WHERE execution_id = ?",
              leidas, insertadas, actualizadas, exec_id)
    stg.commit()
    print(f"OK  execution_id={exec_id}  insertadas={insertadas}  actualizadas={actualizadas}")
except Exception as e:
    dw.rollback()
    s.execute("UPDATE audit.etl_run SET end_time = SYSDATETIME(), status = 'FAILED', error_detail = ? "
              "WHERE execution_id = ?", str(e)[:4000], exec_id)
    stg.commit()
    print("ERR", e)
    sys.exit(1)