import os
import sys

import pyodbc
from dotenv import load_dotenv

load_dotenv()
PIPELINE = "clean_sales"

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={os.getenv('MSSQL_HOST')},{os.getenv('MSSQL_PORT')};DATABASE=WWI_Staging;"
    f"UID={os.getenv('MSSQL_WRITER_USER')};PWD={os.getenv('MSSQL_WRITER_PASSWORD')};"
    "TrustServerCertificate=yes;"
)
cur = conn.cursor()

cur.execute("INSERT audit.etl_run (pipeline_name, source_object, target_object) "
            "OUTPUT INSERTED.execution_id VALUES (?, 'raw.Sales_InvoiceLines', 'clean.Sales_InvoiceLines')",
            PIPELINE)
exec_id = cur.fetchone()[0]
conn.commit()

try:
    cur.execute("SELECT COUNT(*) FROM raw.Sales_InvoiceLines")
    leidas = cur.fetchone()[0]

    cur.execute("EXEC clean.usp_clean_sales ?", exec_id)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM clean.Sales_InvoiceLines")
    limpias = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM quarantine.rejected_rows WHERE execution_id = ?", exec_id)
    rechazadas = cur.fetchone()[0]

    if leidas != limpias + rechazadas:
        raise RuntimeError(f"Conteos no cuadran: leidas={leidas}, limpias={limpias}, rechazadas={rechazadas}")

    cur.execute("UPDATE audit.etl_run SET end_time = SYSDATETIME(), rows_read = ?, rows_inserted = ?, "
                "rows_rejected = ?, status = 'SUCCESS' WHERE execution_id = ?",
                leidas, limpias, rechazadas, exec_id)
    conn.commit()
    print(f"OK  leidas={leidas}  limpias={limpias}  rechazadas={rechazadas}")
except Exception as e:
    conn.rollback()
    cur.execute("UPDATE audit.etl_run SET end_time = SYSDATETIME(), status = 'FAILED', error_detail = ? "
                "WHERE execution_id = ?", str(e)[:4000], exec_id)
    conn.commit()
    print("ERR", e)
    sys.exit(1)