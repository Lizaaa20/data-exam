import os

import pyodbc
from dotenv import load_dotenv

load_dotenv()
usuario = os.getenv("MSSQL_API_USER")
clave = os.getenv("MSSQL_API_PASSWORD") or ""
print("host:", os.getenv("MSSQL_HOST"), "| puerto:", os.getenv("MSSQL_PORT"))
print("usuario:", repr(usuario), "| largo de la clave:", len(clave))

pruebas = {
    "WWI_DW": "SELECT COUNT(*) FROM dw.FactSales",
    "WWI_Staging": "SELECT COUNT(*) FROM audit.etl_run",
}
for db, sql in pruebas.items():
    try:
        cn = pyodbc.connect(
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={os.getenv('MSSQL_HOST')},{os.getenv('MSSQL_PORT')};DATABASE={db};"
            f"UID={usuario};PWD={clave};TrustServerCertificate=yes;",
            timeout=10,
        )
        print(db, "OK, filas:", cn.cursor().execute(sql).fetchone()[0])
        cn.close()
    except Exception as e:
        print(db, "ERROR:", e)