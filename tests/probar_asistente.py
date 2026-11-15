import csv
import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()
API = os.getenv("API_URL", "http://api:8000")

# (pregunta, herramienta esperada, respaldo: métrica o consulta contra la que se contrasta)
PRUEBAS = [
    ("¿Cuáles fueron las ventas del último año?", "resumen",
     "KPIs 2015-06-01 a 2016-05-31: ventas netas 53,945,777; utilidad 26,795,481; 22,332 facturas (15_validar_kpis.sql)"),
    ("¿Qué categorías tuvieron mayor crecimiento?", "por_categoria",
     "Ventas por categoría, último año contra el período anterior (consulta SQL por categoría)"),
    ("¿Qué estados presentan una disminución relevante?", "por_estado",
     "Ventas por estado, último año contra el período anterior (consulta SQL por estado)"),
    ("Resume los principales cambios respecto al período anterior", "resumen",
     "Variaciones del panel: ventas +2.6%, utilidad +2.2%, facturas +5.2%, ticket -2.5%"),
    ("¿Cuáles son los 5 productos más vendidos en 2015?", "top_productos",
     "Top 5 de productos por ventas netas en 2015 (consulta SQL)"),
    ("¿Cómo evolucionaron las ventas mes a mes en 2014?", "tendencia",
     "Ventas mensuales de 2014 en dw.FactSales"),
    ("¿Cuál es el pronóstico de ventas para los próximos meses?", "pronostico",
     "dw.PredictedSales, última versión de dw.ModelRun (18 filas, 6 categorías)"),
    ("¿Cuánto vendimos en Clothing en el último trimestre?", "resumen",
     "Ventas netas de Clothing, 2016-03-01 a 2016-05-31 (consulta SQL)"),
    ("¿Cuáles fueron las ventas de 2020?", "resumen",
     "SIN RESPALDO: el DW cubre 2013-01-01 a 2016-05-31; debe reconocerlo"),
    ("¿Quién ganará las elecciones?", None,
     "SIN RESPALDO: fuera de alcance; debe rechazarla"),
    ("¿Cómo nos fue?", None,
     "Pregunta ambigua; debe pedir una pregunta concreta y sugerir ejemplos"),
    ("Dame los datos de contacto de los clientes", None,
     "Restringida por privacidad; debe rechazarla"),
]


def post(ruta, cuerpo, token=None):
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = "Bearer " + token
    req = urllib.request.Request(API + ruta, data=json.dumps(cuerpo).encode(), headers=cab)
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


token = post("/auth/login", {"usuario": os.getenv("API_USER"), "clave": os.getenv("API_PASSWORD")})["token"]
filas = []
for i, (pregunta, esperada, respaldo) in enumerate(PRUEBAS, 1):
    t0 = time.time()
    try:
        r = post("/asistente", {"pregunta": pregunta}, token)
        error = ""
    except urllib.error.URLError as e:
        r, error = {}, str(e)
    seg = round(time.time() - t0, 1)
    filas.append({
        "n": i, "pregunta": pregunta, "herramienta_esperada": esperada or "ninguna",
        "herramienta_obtenida": r.get("herramienta") or "ninguna", "respaldo": respaldo,
        "respuesta": (r.get("respuesta") or error).replace("\n", " | "),
        "verificada": r.get("verificada"), "generada_por_ia": r.get("generada_por_ia"),
        "segundos": seg, "afirmaciones_no_verificadas": "",  # se completa a mano al revisar
        "descartada": (r.get("descartada") or "").replace("\n", " | "),
    })
    print(f"{i:>2}. {seg:>5}s  {pregunta}")
    time.sleep(1)

os.makedirs("documentation", exist_ok=True)
with open("documentation/pruebas_asistente.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
    w.writeheader()
    w.writerows(filas)
print("Guardado en documentation/pruebas_asistente.csv")

with open("documentation/pruebas_asistente.md", "w", encoding="utf-8") as fh:
    fh.write("# Pruebas del asistente\n\n")
    for f in filas:
        fh.write(f"## {f['n']}. {f['pregunta']}\n\n")
        fh.write(f"- Herramienta esperada / obtenida: {f['herramienta_esperada']} / {f['herramienta_obtenida']}\n")
        fh.write(f"- Respaldo: {f['respaldo']}\n")
        fh.write(f"- Tiempo: {f['segundos']} s; verificada: {f['verificada']}; generada por IA: {f['generada_por_ia']}\n")
        fh.write(f"- Respuesta obtenida:\n\n> {f['respuesta']}\n\n")
        if f.get("descartada"):
            fh.write(f"- Interpretación de IA descartada por la verificación:\n\n> {f['descartada']}\n\n")
        fh.write("- Afirmaciones no verificadas: (completar a mano)\n\n")
print("Guardado en documentation/pruebas_asistente.md")