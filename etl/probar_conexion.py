import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={os.getenv('MSSQL_HOST')},{os.getenv('MSSQL_PORT')};"
    "DATABASE=WWI_Source;"
    f"UID={os.getenv('MSSQL_READER_USER')};"
    f"PWD={os.getenv('MSSQL_READER_PASSWORD')};"
    "TrustServerCertificate=yes;"
)
print(conn.cursor().execute("SELECT COUNT(*) FROM Sales.Invoices").fetchone()[0])