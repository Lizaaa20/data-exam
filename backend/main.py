import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hmac import compare_digest

import jwt
import pyodbc
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

load_dotenv()
log = logging.getLogger("api")

SECRET = os.getenv("API_SECRET", "")
if len(SECRET) < 16:
    raise RuntimeError("Define API_SECRET (mínimo 16 caracteres) en el .env")

app = FastAPI(title="Plataforma de Analítica WWI", version="1.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["X-Tiempo-ms"],
)


@app.middleware("http")
async def medir_tiempo(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Tiempo-ms"] = f"{(time.perf_counter() - t0) * 1000:.0f}"
    return resp


# ---------- Acceso a datos (usuario de solo lectura, consultas parametrizadas) ----------
def consulta(sql: str, params=(), db: str = "WWI_DW") -> list[dict]:
    try:
        cn = pyodbc.connect(
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={os.getenv('MSSQL_HOST')},{os.getenv('MSSQL_PORT')};DATABASE={db};"
            f"UID={os.getenv('MSSQL_API_USER')};PWD={os.getenv('MSSQL_API_PASSWORD')};"
            "TrustServerCertificate=yes;",
            timeout=10,
        )
    except pyodbc.Error:
        log.exception("No se pudo conectar a %s", db)
        raise HTTPException(503, "Data Warehouse no disponible")
    try:
        cur = cn.cursor()
        cur.execute(sql, list(params))
        cols = [c[0] for c in cur.description]
        return [
            {k: (float(v) if isinstance(v, Decimal) else v) for k, v in zip(cols, fila)}
            for fila in cur.fetchall()
        ]
    except pyodbc.Error:
        log.exception("Error en consulta")
        raise HTTPException(500, "Error al consultar los datos")
    finally:
        cn.close()


BASE = (
    "FROM dw.FactSales f "
    "JOIN dw.DimDate d ON d.DateKey = f.DateKey "
    "JOIN dw.DimProduct p ON p.ProductKey = f.ProductKey "
    "JOIN dw.DimCustomer c ON c.CustomerKey = f.CustomerKey "
)


def clausula(desde, hasta, categoria, estado):
    w, p = "WHERE d.FullDate BETWEEN ? AND ?", [desde, hasta]
    if categoria:
        w += " AND p.PrimaryCategory = ?"
        p.append(categoria)
    if estado:
        w += " AND c.StateProvinceName = ?"
        p.append(estado)
    return w, p


# ---------- Autenticación ----------
bearer = HTTPBearer()


class Login(BaseModel):
    usuario: str
    clave: str


@app.post("/auth/login", tags=["auth"])
def login(d: Login):
    u, c = os.getenv("API_USER", ""), os.getenv("API_PASSWORD", "")
    if not u or not c:
        raise HTTPException(503, "Acceso no configurado")
    ok = compare_digest(d.usuario.encode(), u.encode()) & compare_digest(d.clave.encode(), c.encode())
    if not ok:
        raise HTTPException(401, "Usuario o clave incorrectos")
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    return {"token": jwt.encode({"sub": d.usuario, "exp": exp}, SECRET, algorithm="HS256")}


def usuario_actual(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    try:
        return jwt.decode(cred.credentials, SECRET, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Token inválido o vencido")


@app.get("/salud", tags=["meta"])
def salud():
    return {"estado": "ok"}


api = APIRouter(dependencies=[Depends(usuario_actual)])


# ---------- Filtros comunes ----------
def filtros(
    desde: date | None = None,
    hasta: date | None = None,
    categoria: str | None = None,
    estado: str | None = None,
) -> dict:
    if desde is None or hasta is None:
        r = consulta(
            "SELECT MIN(d.FullDate) AS d, MAX(d.FullDate) AS h "
            "FROM dw.FactSales f JOIN dw.DimDate d ON d.DateKey = f.DateKey"
        )[0]
        desde = desde or r["d"] or date.today()
        hasta = hasta or r["h"] or date.today()
    if desde > hasta:
        raise HTTPException(422, "'desde' no puede ser posterior a 'hasta'")
    return {"desde": desde, "hasta": hasta, "categoria": categoria, "estado": estado}


def _w(f: dict):
    return clausula(f["desde"], f["hasta"], f["categoria"], f["estado"])


# ---------- KPIs ----------
def _kpis(desde, hasta, categoria, estado) -> dict:
    w, p = clausula(desde, hasta, categoria, estado)
    r = consulta(
        "SELECT COALESCE(SUM(f.NetSalesAmount), 0) AS ventas_netas, "
        "COALESCE(SUM(f.LineProfit), 0) AS utilidad, "
        "COALESCE(SUM(f.Quantity), 0) AS unidades, "
        f"COUNT(DISTINCT f.InvoiceID) AS facturas {BASE}{w}",
        p,
    )[0]
    v, u, fac = r["ventas_netas"], r["utilidad"], r["facturas"]
    return {
        "ventas_netas": round(v, 2),
        "utilidad": round(u, 2),
        "margen_pct": round(u / v * 100, 2) if v else 0,
        "unidades": int(r["unidades"]),
        "facturas": fac,
        "ticket_promedio": round(v / fac, 2) if fac else 0,
    }


def _var(nombre, actual, previo):
    if nombre == "margen_pct":
        return round(actual - previo, 2)  # diferencia en puntos porcentuales
    return None if not previo else round((actual - previo) / previo * 100, 2)


def _anio_atras(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year - 1, day=28)


@api.get("/kpis", tags=["indicadores"])
def kpis(f: dict = Depends(filtros)):
    actual = _kpis(f["desde"], f["hasta"], f["categoria"], f["estado"])
    dias = (f["hasta"] - f["desde"]).days + 1
    a_hasta = f["desde"] - timedelta(days=1)
    a_desde = a_hasta - timedelta(days=dias - 1)
    y_desde, y_hasta = _anio_atras(f["desde"]), _anio_atras(f["hasta"])