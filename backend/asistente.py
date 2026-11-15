"""Asistente analítico: enruta a consultas aprobadas, redacta con un LLM y verifica las cifras."""
import json
import os
import re
import time
import unicodedata
import urllib.request
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

LLM_URL = os.getenv("LLM_BASE_URL", "http://ollama:11434/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:3b")
LLM_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "240"))
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(RAIZ, "logs", "asistente.jsonl")
LIMITE_POR_MINUTO = 10

consulta = None  # lo asigna crear_router: acceso de solo lectura al DW

BASE = (
    "FROM dw.FactSales f JOIN dw.DimDate d ON d.DateKey = f.DateKey "
    "JOIN dw.DimProduct p ON p.ProductKey = f.ProductKey "
    "JOIN dw.DimCustomer c ON c.CustomerKey = f.CustomerKey "
)
RESTRINGIDO = ("cliente", "contrasena", "password", "correo", "telefono", "direccion de")
HERRAMIENTAS = [
    ("pronostico", ("pronostic", "predic", "proximos meses", "futuro", "proyecc")),
    ("tendencia", ("tendencia", "evolucion", "mes a mes", "mensual")),
    ("top_productos", ("producto", "articulo")),
    ("por_estado", ("estado", "region", "zona", "geograf")),
    ("por_categoria", ("categoria", "crecimiento", "disminu", "cayeron", "bajaron")),
    ("resumen", ("venta", "vend", "ingreso", "utilidad", "ganancia", "margen", "factura", "ticket",
                 "unidades", "resum", "cambio", "indicador", "kpi", "desempeno", "rendimiento")),
]
ETIQUETAS = {
    "ultimo_mes": "último mes con datos",
    "ultimo_trimestre": "últimos 3 meses",
    "ultimo_anio": "últimos 12 meses",
    "todo": "todo el histórico",
}
SISTEMA = (
    "Eres un analista de ventas. Con los datos entregados escribe UNA interpretación breve (2 frases) en español. "
    "Reglas: usa solo los datos entregados; no inventes causas, cifras, meses ni fechas; si citas una cifra, "
    "cópiala exactamente; un porcentaje negativo es una disminución y uno positivo es un aumento; "
    "no uses 'crecimiento' para valores negativos; si son predicciones, dilo."
)


class Pregunta(BaseModel):
    pregunta: str = Field(min_length=3, max_length=300)


# ---------- Utilidades ----------
def norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


_visitas = defaultdict(deque)


def controlar_frecuencia(usuario: str):
    ahora, cola = time.time(), _visitas[usuario]
    while cola and ahora - cola[0] > 60:
        cola.popleft()
    if len(cola) >= LIMITE_POR_MINUTO:
        raise HTTPException(429, "Demasiadas preguntas por minuto. Espera unos segundos.")
    cola.append(ahora)


def registrar(usuario, pregunta, herramienta, verificada, ms):
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "usuario": usuario, "pregunta": pregunta[:300], "herramienta": herramienta,
                "verificada": verificada, "ms": ms}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def base(**extra):
    d = {"respuesta": "", "herramienta": None, "periodo": None, "tipo": "sin_datos", "verificada": True,
         "generada_por_ia": False, "fuente": "WWI_DW", "aviso": None, "datos": None, "datos_texto": None,
         "modelo": None}
    d.update(extra)
    return d


def a_texto(d) -> str:
    lineas = []
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                lineas.append(f"{k}:")
                lineas.append(a_texto(v))
            else:
                lineas.append(f"{k}: {v}")
    elif isinstance(d, list):
        for it in d:
            if isinstance(it, dict):
                lineas.append("- " + ", ".join(f"{k} {v}" for k, v in it.items()))
            else:
                lineas.append(f"- {it}")
    return "\n".join(lineas)


# ---------- Períodos y filtros ----------
def mes_menos(d: date, k: int) -> date:
    m = d.year * 12 + (d.month - 1) - k
    return date(m // 12, m % 12 + 1, 1)


def clave_periodo(q, minimo, ref):
    m = re.search(r"\b(19|20)\d{2}\b", q)
    if m:
        anio = int(m.group(0))
        return anio if minimo.year <= anio <= ref.year else ("sin_datos", anio)
    if "ultimo mes" in q or "mes pasado" in q or "este mes" in q:
        return "ultimo_mes"
    if "trimestre" in q:
        return "ultimo_trimestre"
    if "historic" in q or "todo el periodo" in q or "desde el inicio" in q:
        return "todo"
    return "ultimo_anio"


def resolver(clave, minimo, ref):
    if clave == "todo":
        return minimo, ref
    if clave == "ultimo_mes":
        return ref.replace(day=1), ref
    if clave == "ultimo_trimestre":
        return mes_menos(ref, 2), ref
    if isinstance(clave, int):
        return max(date(clave, 1, 1), minimo), min(date(clave, 12, 31), ref)
    d = ref + timedelta(days=1)
    try:
        d = d.replace(year=d.year - 1)
    except ValueError:
        d = d - timedelta(days=365)
    return max(d, minimo), ref


def periodo_previo(per, minimo):
    dias = (per[1] - per[0]).days + 1
    hasta = per[0] - timedelta(days=1)
    desde = hasta - timedelta(days=dias - 1)
    return (desde, hasta) if desde >= minimo else None


def donde(desde, hasta, categoria=None, estado=None):
    w, p = "WHERE d.FullDate BETWEEN ? AND ?", [desde, hasta]
    if categoria:
        w += " AND p.PrimaryCategory = ?"
        p.append(categoria)
    if estado:
        w += " AND c.StateProvinceName = ?"
        p.append(estado)
    return w, p


def detectar(q):
    cats = [r["v"] for r in consulta("SELECT DISTINCT PrimaryCategory AS v FROM dw.DimProduct WHERE ProductKey <> -1")]
    ests = [r["v"] for r in consulta("SELECT DISTINCT StateProvinceName AS v FROM dw.DimCustomer WHERE CustomerKey <> -1")]
    return next((c for c in cats if norm(c) in q), None), next((e for e in ests if norm(e) in q), None)


# ---------- Herramientas aprobadas (consultas parametrizadas, solo lectura) ----------
def _kpis(desde, hasta, categoria, estado):
    w, p = donde(desde, hasta, categoria, estado)
    r = consulta(
        "SELECT COALESCE(SUM(f.NetSalesAmount), 0) AS ventas_netas, COALESCE(SUM(f.LineProfit), 0) AS utilidad, "
        "COALESCE(SUM(f.Quantity), 0) AS unidades, COUNT(DISTINCT f.InvoiceID) AS facturas " + BASE + w, p)[0]
    v, u, fac = r["ventas_netas"], r["utilidad"], r["facturas"]
    return {"ventas_netas": round(v, 2), "utilidad": round(u, 2),
            "margen_pct": round(u / v * 100, 2) if v else 0, "unidades": int(r["unidades"]),
            "facturas": fac, "ticket_promedio": round(v / fac, 2) if fac else 0}


def t_resumen(per, prev, cat, est):
    act = _kpis(per[0], per[1], cat, est)
    datos = {"actual": act}
    if prev:
        ant = _kpis(prev[0], prev[1], cat, est)
        if ant["facturas"]:
            datos["periodo_anterior"] = f"{prev[0]} a {prev[1]}"
            datos["anterior"] = ant
            datos["variacion_pct"] = {k: round((act[k] - ant[k]) / ant[k] * 100, 1)
                                      for k in ("ventas_netas", "utilidad", "unidades", "facturas", "ticket_promedio")
                                      if ant[k]}
            datos["variacion_margen_puntos"] = round(act["margen_pct"] - ant["margen_pct"], 2)
    return datos


def t_desglose(campo, per, prev, cat, est, limite, orden=None):
    col = "p.PrimaryCategory" if campo == "categoria" else "c.StateProvinceName"
    desde = prev[0] if prev else per[0]
    w, p = donde(desde, per[1], cat if campo == "estado" else None, est if campo == "categoria" else None)
    pd, ph = prev if prev else (date(1900, 1, 1), date(1900, 1, 1))
    filas = consulta(
        f"SELECT {col} AS nombre, "
        "SUM(CASE WHEN d.FullDate BETWEEN ? AND ? THEN f.NetSalesAmount ELSE 0 END) AS ventas, "
        "SUM(CASE WHEN d.FullDate BETWEEN ? AND ? THEN f.NetSalesAmount ELSE 0 END) AS ventas_anterior "
        + BASE + w + f" GROUP BY {col}",
        [per[0], per[1], pd, ph] + p)
    salida = []
    for f in sorted(filas, key=lambda x: -x["ventas"]):
        if f["ventas"] <= 0 and f["ventas_anterior"] <= 0:
            continue
        item = {"nombre": f["nombre"], "ventas": round(f["ventas"])}
        if prev:
            item["ventas_periodo_anterior"] = round(f["ventas_anterior"])
            item["crecimiento_pct"] = (round((f["ventas"] - f["ventas_anterior"]) / f["ventas_anterior"] * 100, 1)
                                       if f["ventas_anterior"] > 0 else "sin ventas en el período anterior")
        salida.append(item)
    if orden and prev:
        con_dato = [x for x in salida if isinstance(x.get("crecimiento_pct"), (int, float))]
        salida = sorted(con_dato, key=lambda x: x["crecimiento_pct"], reverse=(orden == "crec"))
    datos = {"filas": salida[:limite]}
    if prev:
        datos["periodo_anterior"] = f"{prev[0]} a {prev[1]}"
    else:
        datos["nota"] = "No hay período anterior comparable dentro de los datos."
    return datos


def t_top_productos(per, cat, est):
    w, p = donde(per[0], per[1], cat, est)
    filas = consulta(
        "SELECT TOP 5 p.StockItemName AS nombre, SUM(f.NetSalesAmount) AS ventas, SUM(f.Quantity) AS unidades "
        + BASE + w + " GROUP BY p.StockItemName ORDER BY ventas DESC", p)
    return {"filas": [{"nombre": f["nombre"], "ventas": round(f["ventas"]), "unidades": int(f["unidades"])}
                      for f in filas]}


def t_tendencia(per, cat, est):
    w, p = donde(per[0], per[1], cat, est)
    filas = consulta("SELECT d.YearMonth AS mes, SUM(f.NetSalesAmount) AS ventas " + BASE + w
                     + " GROUP BY d.YearMonth ORDER BY d.YearMonth", p)
    return {"filas": [{"mes": f["mes"], "ventas": round(f["ventas"])} for f in filas][-12:],
            "nota": "Se muestran como máximo los últimos 12 meses del período."}


def t_pronostico():
    run = consulta("SELECT TOP 1 ModelVersion, ModelName, MaeTest, BaselineName, BaselineMaeTest "
                   "FROM dw.ModelRun ORDER BY TrainedAt DESC")
    if not run:
        return None
    m = run[0]
    filas = consulta("SELECT Category AS nombre, TargetMonth AS mes, PredictedSales AS ventas "
                     "FROM dw.PredictedSales WHERE ModelVersion = ?", [m["ModelVersion"]])
    por_mes, por_cat = defaultdict(float), defaultdict(float)
    for f in filas:
        por_mes[f["mes"]] += f["ventas"]
        por_cat[f["nombre"]] += f["ventas"]
    return {
        "modelo": m["ModelName"],
        "error_medio_en_prueba": round(m["MaeTest"]),
        "error_medio_linea_base": round(m["BaselineMaeTest"]),
        "total_por_mes": [{"mes": k, "ventas": round(v)} for k, v in sorted(por_mes.items())],
        "total_3_meses_por_categoria": [{"nombre": k, "ventas": round(v)}
                                        for k, v in sorted(por_cat.items(), key=lambda x: -x[1])],
        "nota": "Son predicciones, no ventas reales. No incluye categorías con menos de 24 meses de historia.",
    }


# ---------- LLM y verificación ----------
def llamar_llm(sistema: str, usuario: str) -> str:
    cuerpo = json.dumps({"model": LLM_MODEL, "temperature": 0, "max_tokens": 250,
                         "messages": [{"role": "system", "content": sistema},
                                      {"role": "user", "content": usuario}]}).encode()
    req = urllib.request.Request(LLM_URL.rstrip("/") + "/chat/completions", data=cuerpo,
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + LLM_KEY})
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


FECHA = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")
NUMERO = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
NEG = ("disminu", "cay", "baj", "descen", "reduc", "retroce")
POS = ("aument", "crec", "sub", "increment", "mejor", "ascend")
PORCENTAJE = re.compile(r"(-?\d+(?:\.\d+)?)\s?%")


def hojas(d, out, con_signo=False):
    if isinstance(d, dict):
        for v in d.values():
            hojas(v, out, con_signo)
    elif isinstance(d, (list, tuple)):
        for v in d:
            hojas(v, out, con_signo)
    elif isinstance(d, (int, float)) and not isinstance(d, bool):
        out.append(float(d) if con_signo else abs(float(d)))
    return out


def cadenas(d, out):
    if isinstance(d, dict):
        for v in d.values():
            cadenas(v, out)
    elif isinstance(d, (list, tuple)):
        for v in d:
            cadenas(v, out)
    elif isinstance(d, str):
        out.append(d)
    return out


def verificar(texto: str, datos) -> bool:
    """Cada cifra debe estar en los datos y, en porcentajes, el signo debe ser coherente con el verbo cercano."""
    limpio = texto
    for s in sorted(cadenas(datos, []), key=len, reverse=True):
        if len(s) > 3:
            limpio = limpio.replace(s, " ")  # los números dentro de nombres no son cifras
    permitidos = hojas(datos, [])
    for s in NUMERO.findall(FECHA.sub(" ", limpio)):
        x = abs(float(s.replace(",", "")))
        if x == int(x) and (x <= 12 or 1990 <= x <= 2100):
            continue
        if not any(abs(x * esc - v) <= max(0.51, 0.01 * v) for v in permitidos for esc in (1, 1e3, 1e6, 1e9)):
            return False
    firmados = hojas(datos, [], con_signo=True)
    for m in PORCENTAJE.finditer(limpio):
        x = float(m.group(1))
        ventana = norm(limpio[max(0, m.start() - 45): m.start()])
        coincide = [v for v in firmados if abs(abs(v) - abs(x)) <= 0.06]
        if not coincide:
            continue
        hay_neg = any(k in ventana for k in NEG)
        hay_pos = any(k in ventana for k in POS)
        if x < 0 and not any(v < 0 for v in coincide):
            return False
        if hay_neg and not hay_pos and not any(v < 0 for v in coincide):
            return False
        if hay_pos and not hay_neg and not any(v > 0 for v in coincide):
            return False
    return True


def _m(x):
    return f"${x:,.0f}"


def _p(x, dec=1):
    if not isinstance(x, (int, float)):
        return "n/d"
    return f"{round(x, dec) + 0.0:+.{dec}f}%"


def hechos(herramienta, d):
    """Texto armado por el código con las cifras exactas: no lo escribe el modelo."""
    if herramienta == "resumen":
        a = d["actual"]
        l = [f"Ventas netas: {_m(a['ventas_netas'])}",
             f"Utilidad: {_m(a['utilidad'])} (margen {a['margen_pct']:.2f}%)",
             f"Unidades: {a['unidades']:,}", f"Facturas: {a['facturas']:,}",
             f"Ticket promedio: ${a['ticket_promedio']:,.2f}"]
        if "variacion_pct" in d:
            v = d["variacion_pct"]
            l.append(f"Frente a {d['periodo_anterior']}: ventas {_p(v.get('ventas_netas'))}, "
                     f"utilidad {_p(v.get('utilidad'))}, unidades {_p(v.get('unidades'))}, "
                     f"facturas {_p(v.get('facturas'))}, ticket {_p(v.get('ticket_promedio'))}, "
                     f"margen {d['variacion_margen_puntos']:+.2f} puntos porcentuales")
        return "\n".join(l)
    if herramienta in ("por_categoria", "por_estado"):
        l = []
        for f in d["filas"]:
            linea = f"- {f['nombre']}: {_m(f['ventas'])}"
            if "crecimiento_pct" in f:
                c = f["crecimiento_pct"]
                linea += f" (frente al período anterior: {_p(c) if isinstance(c, (int, float)) else c})"
            l.append(linea)
        if d.get("periodo_anterior"):
            l.append(f"Período de comparación: {d['periodo_anterior']}")
        if d.get("nota"):
            l.append(d["nota"])
        return "\n".join(l)
    if herramienta == "top_productos":
        return "\n".join(f"- {f['nombre']}: {_m(f['ventas'])}, {f['unidades']:,} unidades" for f in d["filas"])
    if herramienta == "tendencia":
        return "\n".join([f"- {f['mes']}: {_m(f['ventas'])}" for f in d["filas"]] + [d["nota"]])
    l = [f"Modelo {d['modelo']}: error medio en prueba {_m(d['error_medio_en_prueba'])} "
         f"(mejor línea base: {_m(d['error_medio_linea_base'])})", "Total pronosticado por mes:"]
    l += [f"- {f['mes']}: {_m(f['ventas'])}" for f in d["total_por_mes"]]
    l.append("Total de los 3 meses por categoría:")
    l += [f"- {f['nombre']}: {_m(f['ventas'])}" for f in d["total_3_meses_por_categoria"]]
    l.append(d["nota"])
    return "\n".join(l)


IA_PERMITIDA = ("resumen", "pronostico")  # en rankings y tendencias el código calcula todo


def redactar(pregunta, herramienta, datos, periodo, tipo, aviso=None):
    texto = a_texto(datos)
    cuerpo = ("Pronóstico (predicción del modelo, no ventas reales):\n" if tipo == "prediccion"
              else "Datos consultados:\n") + hechos(herramienta, datos)
    salida = base(herramienta=herramienta, periodo=periodo, tipo=tipo, datos=datos, datos_texto=texto,
                  aviso=aviso, modelo=LLM_MODEL, respuesta=cuerpo)
    pref = (aviso + " ") if aviso else ""
    if herramienta not in IA_PERMITIDA:
        salida.update(aviso=pref + "Los rankings, comparaciones y tendencias los calcula el código; no se usa IA "
                                   "para interpretarlos porque puede equivocarse al compararlos.")
        return salida
    try:
        interp = llamar_llm(SISTEMA, f"Pregunta: {pregunta}\nPeríodo: {periodo}\nDatos:\n{texto}")
    except Exception:
        salida.update(aviso=pref + "Sin interpretación de IA (el modelo no está disponible).")
        return salida
    if verificar(interp, datos):
        salida.update(respuesta=cuerpo + "\n\nInterpretación generada por IA "
                                         "(solo se verifican las cifras, no las comparaciones):\n" + interp,
                      generada_por_ia=True)
    else:
        salida.update(verificada=False, descartada=interp,
                      aviso=pref + "La interpretación de IA se descartó porque no coincidía con los datos.")
    return salida


# ---------- Flujo principal ----------
def ultima_carga():
    try:
        return consulta("SELECT MAX(end_time) AS u FROM audit.etl_run WHERE pipeline_name = 'load_dw' "
                        "AND status = 'SUCCESS'", db="WWI_Staging")[0]["u"]
    except Exception:
        return None


def _responder(pregunta, q):
    if any(k in q for k in RESTRINGIDO):
        return base(respuesta="Por privacidad, el asistente no entrega datos de clientes individuales ni "
                              "credenciales. Puedo responder sobre ventas por categoría, estado, producto o período.")
    herramienta = enrutar(q)
    if herramienta is None:
        return base(respuesta="No puedo responder eso con los datos disponibles. Puedo informar sobre ventas, "
                              "utilidad, margen, categorías, estados, productos, tendencias y el pronóstico de "
                              "ventas. Prueba, por ejemplo: «¿Qué categorías tuvieron mayor crecimiento?».")
    aviso = ("El Data Warehouse agrupa la geografía por estado de EE. UU.; la región es la misma para todos los "
             "clientes.") if "region" in q else None

    if herramienta == "pronostico":
        datos = t_pronostico()
        if not datos:
            return base(respuesta="Todavía no hay un modelo de pronóstico entrenado.", herramienta=herramienta)
        return redactar(pregunta, herramienta, datos, "próximos 3 meses después del último dato", "prediccion", aviso)

    rango = consulta("SELECT MIN(d.FullDate) AS a, MAX(d.FullDate) AS b FROM dw.FactSales f "
                     "JOIN dw.DimDate d ON d.DateKey = f.DateKey")[0]
    minimo, ref = rango["a"], rango["b"]
    clave = clave_periodo(q, minimo, ref)
    if isinstance(clave, tuple):
        return base(respuesta=f"No hay datos de {clave[1]}. El Data Warehouse cubre de {minimo} a {ref}.",
                    herramienta=herramienta)

    cat, est = detectar(q)
    per = resolver(clave, minimo, ref)
    prev = periodo_previo(per, minimo)
    orden = None
    if any(k in q for k in ("disminu", "cayeron", "bajaron", "caida", "descenso", "retroce")):
        orden = "caida"
    elif any(k in q for k in ("crecimiento", "crecieron", "aument", "mayor")):
        orden = "crec"

    if herramienta == "resumen":
        datos = t_resumen(per, prev, cat, est)
        vacio = datos["actual"]["facturas"] == 0
    elif herramienta == "por_categoria":
        datos = t_desglose("categoria", per, prev, cat, est, 10, orden)
        vacio = not datos["filas"]
    elif herramienta == "por_estado":
        datos = t_desglose("estado", per, prev, cat, est, 8, orden)
        vacio = not datos["filas"]
    elif herramienta == "top_productos":
        datos = t_top_productos(per, cat, est)
        vacio = not datos["filas"]
    else:
        datos = t_tendencia(per, cat, est)
        vacio = not datos["filas"]

    desc = f"{per[0]} a {per[1]}" + (f", categoría {cat}" if cat else "") + (f", estado {est}" if est else "")
    if not isinstance(clave, int):
        desc += f" ({ETIQUETAS[clave]})"
    if vacio:
        return base(respuesta=f"No hay ventas registradas para {desc}.", herramienta=herramienta, periodo=desc)
    return redactar(pregunta, herramienta, datos, desc, "historico", aviso)





def enrutar(q):
    for nombre, claves in HERRAMIENTAS:
        if any(c in q for c in claves):
            return nombre
    return None


def crear_router(fn_consulta, usuario_dep):
    global consulta
    consulta = fn_consulta
    router = APIRouter()

    @router.post("/asistente", tags=["asistente"])
    def asistente(p: Pregunta, usuario: str = Depends(usuario_dep)):
        t0 = time.perf_counter()
        controlar_frecuencia(usuario)
        r = _responder(p.pregunta.strip(), norm(p.pregunta))
        r["actualizado"] = ultima_carga()
        r["tiempo_ms"] = int((time.perf_counter() - t0) * 1000)
        registrar(usuario, p.pregunta, r.get("herramienta"), r.get("verificada"), r["tiempo_ms"])
        return r

    return router