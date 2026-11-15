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

app = FastAPI(title="Plataforma de Analítica WWI", version="1.0")
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


def clausula(desde, hasta, categoria, region):
    w, p = "WHERE d.FullDate BETWEEN ? AND ?", [desde, hasta]
    if categoria:
        w += " AND p.PrimaryCategory = ?"
        p.append(categoria)
    if region:
        w += " AND c.Region = ?"
        p.append(region)
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
    region: str | None = None,
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
    return {"desde": desde, "hasta": hasta, "categoria": categoria, "region": region}


def _w(f: dict):
    return clausula(f["desde"], f["hasta"], f["categoria"], f["region"])


# ---------- KPIs ----------
def _kpis(desde, hasta, categoria, region) -> dict:
    w, p = clausula(desde, hasta, categoria, region)
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
    actual = _kpis(f["desde"], f["hasta"], f["categoria"], f["region"])
    dias = (f["hasta"] - f["desde"]).days + 1
    a_hasta = f["desde"] - timedelta(days=1)
    a_desde = a_hasta - timedelta(days=dias - 1)
    y_desde, y_hasta = _anio_atras(f["desde"]), _anio_atras(f["hasta"])

    def comparar(desde, hasta):
        k = _kpis(desde, hasta, f["categoria"], f["region"])
        return {
            "desde": desde,
            "hasta": hasta,
            "kpis": k,
            "variacion": {n: _var(n, actual[n], k[n]) for n in actual},
        }

    return {
        "filtros": f,
        "actual": actual,
        "periodo_anterior": comparar(a_desde, a_hasta),
        "anio_anterior": comparar(y_desde, y_hasta),
    }


# ---------- Tendencias y desgloses ----------
GRANULARIDAD = {
    "mes": "d.YearMonth",
    "trimestre": "CONCAT(d.YearNum, '-T', d.QuarterNum)",
    "anio": "CAST(d.YearNum AS VARCHAR(4))",
}


@api.get("/ventas/tendencia", tags=["ventas"])
def tendencia(f: dict = Depends(filtros), granularidad: str = Query("mes", pattern="^(mes|trimestre|anio)$")):
    w, p = _w(f)
    expr = GRANULARIDAD[granularidad]  # valor de lista cerrada, no del usuario
    return consulta(
        f"SELECT {expr} AS periodo, SUM(f.NetSalesAmount) AS ventas_netas, "
        f"SUM(f.LineProfit) AS utilidad, SUM(f.Quantity) AS unidades {BASE}{w} "
        f"GROUP BY {expr} ORDER BY MIN(d.FullDate)",
        p,
    )


@api.get("/ventas/por-categoria", tags=["ventas"])
def por_categoria(f: dict = Depends(filtros)):
    w, p = _w(f)
    return consulta(
        "SELECT p.PrimaryCategory AS categoria, SUM(f.NetSalesAmount) AS ventas_netas, "
        f"SUM(f.LineProfit) AS utilidad {BASE}{w} GROUP BY p.PrimaryCategory ORDER BY ventas_netas DESC",
        p,
    )


@api.get("/ventas/por-region", tags=["ventas"])
def por_region(f: dict = Depends(filtros)):
    w, p = _w(f)
    return consulta(
        "SELECT c.Region AS region, SUM(f.NetSalesAmount) AS ventas_netas, "
        f"SUM(f.LineProfit) AS utilidad {BASE}{w} GROUP BY c.Region ORDER BY ventas_netas DESC",
        p,
    )


@api.get("/ventas/top-productos", tags=["ventas"])
def top_productos(f: dict = Depends(filtros), limite: int = Query(10, ge=1, le=50)):
    w, p = _w(f)
    return consulta(
        "SELECT TOP (?) p.StockItemName AS producto, p.PrimaryCategory AS categoria, "
        f"SUM(f.NetSalesAmount) AS ventas_netas, SUM(f.Quantity) AS unidades {BASE}{w} "
        "GROUP BY p.StockItemName, p.PrimaryCategory ORDER BY ventas_netas DESC",
        [limite] + p,
    )


@api.get("/ventas/top-clientes", tags=["ventas"])
def top_clientes(f: dict = Depends(filtros), limite: int = Query(10, ge=1, le=50)):
    w, p = _w(f)
    return consulta(
        "SELECT TOP (?) c.CustomerID AS cliente_id, MAX(c.CustomerName) AS cliente, "
        f"SUM(f.NetSalesAmount) AS ventas_netas {BASE}{w} "
        "GROUP BY c.CustomerID ORDER BY ventas_netas DESC",
        [limite] + p,
    )


@api.get("/ventas/detalle", tags=["ventas"])
def detalle(
    f: dict = Depends(filtros),
    pagina: int = Query(1, ge=1),
    tamano: int = Query(25, ge=1, le=200),
):
    w, p = _w(f)
    total = consulta(f"SELECT COUNT(*) AS n {BASE}{w}", p)[0]["n"]
    filas = consulta(
        "SELECT d.FullDate AS fecha, f.InvoiceID AS factura, f.InvoiceLineID AS linea, "
        "c.CustomerName AS cliente, p.StockItemName AS producto, p.PrimaryCategory AS categoria, "
        "c.Region AS region, f.Quantity AS cantidad, f.NetSalesAmount AS ventas_netas, "
        f"f.LineProfit AS utilidad {BASE}{w} "
        "ORDER BY d.FullDate DESC, f.InvoiceLineID DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY",
        p + [(pagina - 1) * tamano, tamano],
    )
    return {"total": total, "pagina": pagina, "tamano": tamano, "filas": filas}


# ---------- Metadatos ----------
@api.get("/meta/filtros", tags=["meta"])
def meta_filtros():
    cats = consulta("SELECT DISTINCT PrimaryCategory AS v FROM dw.DimProduct WHERE ProductKey <> -1 ORDER BY 1")
    regs = consulta("SELECT DISTINCT Region AS v FROM dw.DimCustomer WHERE CustomerKey <> -1 ORDER BY 1")
    rango = consulta(
        "SELECT MIN(d.FullDate) AS desde, MAX(d.FullDate) AS hasta "
        "FROM dw.FactSales f JOIN dw.DimDate d ON d.DateKey = f.DateKey"
    )[0]
    return {"categorias": [c["v"] for c in cats], "regiones": [r["v"] for r in regs], "rango_fechas": rango}


@api.get("/meta/ultima-actualizacion", tags=["meta"])
def ultima_actualizacion():
    r = consulta(
        "SELECT MAX(end_time) AS ultima_carga FROM audit.etl_run "
        "WHERE pipeline_name = 'load_dw' AND status = 'SUCCESS'",
        db="WWI_Staging",
    )[0]
    return {"ultima_carga": r["ultima_carga"]}


app.include_router(api)