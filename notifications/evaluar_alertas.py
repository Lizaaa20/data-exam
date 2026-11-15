"""Evalúa reglas de negocio y del modelo, registra alertas sin duplicados y envía correos con reintentos."""
import argparse
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage

import pyodbc
from dotenv import load_dotenv

load_dotenv()
MAX_INTENTOS = 5
MESES_REFERENCIA = 3
SMTP_HOST = os.getenv("SMTP_HOST", "mailpit")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
MAIL_DE = os.getenv("ALERT_EMAIL_FROM", "alertas@wwi.local")
MAIL_PARA = os.getenv("ALERT_EMAIL_TO", "equipo@wwi.local")
ACCION = "Revisar en el dashboard los productos y estados con mayor caída y confirmar si es un efecto estacional."


def conectar():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.getenv('MSSQL_HOST')},{os.getenv('MSSQL_PORT')};DATABASE=WWI_DW;"
        f"UID={os.getenv('MSSQL_WRITER_USER')};PWD={os.getenv('MSSQL_WRITER_PASSWORD')};"
        "TrustServerCertificate=yes;"
    )


def severidad(caida):
    return "ALTA" if caida >= 30 else "MEDIA" if caida >= 15 else "BAJA"


def ventas_mensuales(cur):
    cur.execute(
        "SELECT d.YearMonth, p.PrimaryCategory, SUM(f.NetSalesAmount) "
        "FROM dw.FactSales f JOIN dw.DimDate d ON d.DateKey = f.DateKey "
        "JOIN dw.DimProduct p ON p.ProductKey = f.ProductKey WHERE p.ProductKey <> -1 "
        "GROUP BY d.YearMonth, p.PrimaryCategory"
    )
    series = {}
    for mes, cat, v in cur.fetchall():
        series.setdefault(cat, {})[mes.strip()] = float(v)
    meses = sorted({m for s in series.values() for m in s})
    total = {m: sum(s.get(m, 0.0) for s in series.values()) for m in meses}
    series["Total"] = total
    return series, meses


def promedio(s, meses):
    return sum(s.get(m, 0.0) for m in meses) / len(meses)


def alerta(tipo, ent, obs, ref, umbral, periodo, origen, explicacion, dedup, version=None):
    cambio = (obs - ref) / ref * 100
    return {"tipo": tipo, "sev": severidad(-cambio), "indicador": "ventas_netas", "entidad": ent,
            "obs": round(obs, 2), "ref": round(ref, 2), "cambio": round(cambio, 2), "umbral": umbral,
            "periodo": periodo, "origen": origen, "version": version, "explicacion": explicacion[:500],
            "accion": ACCION, "dedup": dedup}


def reglas_ventas(series, meses, umbral):
    ult, previos = meses[-1], meses[-1 - MESES_REFERENCIA:-1]
    periodo = f"promedio de {previos[0]} a {previos[-1]}"
    for ent, s in series.items():
        ref = promedio(s, previos)
        if ref <= 0:
            continue
        obs = s.get(ult, 0.0)
        if (obs - ref) / ref * 100 <= -umbral:
            texto = (f"Las ventas netas de {ent} en {ult} fueron ${obs:,.0f}, "
                     f"{abs((obs - ref) / ref * 100):.1f}% menos que el {periodo} (${ref:,.0f}).")
            yield alerta("CAIDA_VENTAS", ent, obs, ref, umbral, periodo, "REGLA", texto,
                         f"CAIDA_VENTAS|{ent}|{ult}|u{umbral:g}")


def reglas_modelo(cur, series, meses, umbral):
    cur.execute("SELECT TOP 1 ModelVersion FROM dw.ModelRun ORDER BY TrainedAt DESC")
    fila = cur.fetchone()
    if not fila:
        return
    version, previos = fila[0], meses[-MESES_REFERENCIA:]
    periodo = f"promedio de {previos[0]} a {previos[-1]}"
    cur.execute("SELECT Category, TargetMonth, PredictedSales FROM dw.PredictedSales "
                "WHERE ModelVersion = ? AND HorizonMonths = 1", version)
    for cat, mes, pred in cur.fetchall():
        ref = promedio(series.get(cat, {}), previos)
        if ref <= 0:
            continue
        pred = float(pred)
        if (pred - ref) / ref * 100 <= -umbral:
            texto = (f"El modelo {version} pronostica para {cat.strip()} en {mes.strip()} ventas de ${pred:,.0f}, "
                     f"{abs((pred - ref) / ref * 100):.1f}% menos que el {periodo} (${ref:,.0f}). Es una predicción.")
            yield alerta("DEMANDA_BAJA", cat, pred, ref, umbral, periodo, "MODELO", texto,
                         f"DEMANDA_BAJA|{cat}|{mes.strip()}|u{umbral:g}", version)


def simulada(series, meses, umbral):
    previos = meses[-1 - MESES_REFERENCIA:-1]
    ref = promedio(series["Total"], previos)
    periodo = f"promedio de {previos[0]} a {previos[-1]}"
    texto = ("SIMULACIÓN para la demostración, no es un dato real: ventas del Total simuladas un 30% por "
             f"debajo del {periodo} (${ref:,.0f}).")
    return alerta("CAIDA_VENTAS", "Total", ref * 0.70, ref, umbral, periodo, "SIMULACION", texto,
                  f"SIMULACION|{datetime.now():%Y%m%d%H%M%S}")


def crear_alerta(cur, a):
    cur.execute("SELECT 1 FROM dw.Alert WHERE DedupKey = ?", a["dedup"])
    if cur.fetchone():
        return False
    cur.execute(
        "INSERT dw.Alert (AlertType, Severity, Indicator, Entity, ObservedValue, ReferenceValue, ChangePct, "
        "ThresholdPct, ReferencePeriod, Source, ModelVersion, Explanation, RecommendedAction, DedupKey) "
        "OUTPUT INSERTED.AlertId VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        a["tipo"], a["sev"], a["indicador"], a["entidad"], a["obs"], a["ref"], a["cambio"], a["umbral"],
        a["periodo"], a["origen"], a["version"], a["explicacion"], a["accion"], a["dedup"])
    alerta_id = cur.fetchone()[0]
    cur.execute("INSERT dw.AlertDelivery (AlertId, Channel, Status, Attempts, LastAttemptAt, DeliveredAt) "
                "VALUES (?, 'DASHBOARD', 'ENVIADA', 1, SYSDATETIME(), SYSDATETIME())", alerta_id)
    cur.execute("INSERT dw.AlertDelivery (AlertId, Channel) VALUES (?, 'EMAIL')", alerta_id)
    return True


def texto_correo(a):
    origen = a["Source"] + (f" (modelo {a['ModelVersion']})" if a["ModelVersion"] else "")
    return "\n".join([
        f"Alerta #{a['AlertId']} - {a['CreatedAt']:%Y-%m-%d %H:%M}",
        f"Tipo: {a['AlertType']} | Severidad: {a['Severity']} | Origen: {origen}",
        f"Indicador: {a['Indicator']} | Entidad: {a['Entity']}",
        f"Valor observado o predicho: ${a['ObservedValue']:,.2f} | Referencia: ${a['ReferenceValue']:,.2f} "
        f"({a['ReferencePeriod']})",
        f"Variación: {float(a['ChangePct']):+.1f}% | Umbral: -{float(a['ThresholdPct']):g}%",
        f"Explicación: {a['Explanation']}",
        f"Acción recomendada: {a['RecommendedAction']}",
        f"Estado: {a['Status']}",
    ])


def enviar_pendientes(cn):
    cur = cn.cursor()
    cur.execute(
        "SELECT d.DeliveryId, a.AlertId, a.CreatedAt, a.AlertType, a.Severity, a.Indicator, a.Entity, "
        "a.ObservedValue, a.ReferenceValue, a.ChangePct, a.ThresholdPct, a.ReferencePeriod, a.Source, "
        "a.ModelVersion, a.Explanation, a.RecommendedAction, a.Status "
        "FROM dw.AlertDelivery d JOIN dw.Alert a ON a.AlertId = d.AlertId "
        "WHERE d.Channel = 'EMAIL' AND d.Status <> 'ENVIADA' AND d.Attempts < ? ORDER BY a.AlertId",
        MAX_INTENTOS)
    cols = [c[0] for c in cur.description]
    pendientes = [dict(zip(cols, f)) for f in cur.fetchall()]
    ok = mal = 0
    for a in pendientes:
        msg = EmailMessage()
        msg["Subject"] = f"[{a['Severity']}] {a['AlertType']}: {a['Entity']} ({a['Source']})"
        msg["From"], msg["To"] = MAIL_DE, MAIL_PARA
        msg.set_content(texto_correo(a))
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
                s.send_message(msg)
            cur.execute("UPDATE dw.AlertDelivery SET Status = 'ENVIADA', Attempts = Attempts + 1, "
                        "LastAttemptAt = SYSDATETIME(), DeliveredAt = SYSDATETIME(), LastError = NULL "
                        "WHERE DeliveryId = ?", a["DeliveryId"])
            ok += 1
        except Exception as e:
            cur.execute("UPDATE dw.AlertDelivery SET Status = 'FALLIDA', Attempts = Attempts + 1, "
                        "LastAttemptAt = SYSDATETIME(), LastError = ? WHERE DeliveryId = ?",
                        str(e)[:400], a["DeliveryId"])
            mal += 1
        cn.commit()
    return ok, mal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral", type=float, default=15.0, help="caída mínima en %% para disparar (por defecto 15)")
    ap.add_argument("--simular", action="store_true", help="agrega una alerta SIMULADA para la demostración")
    ap.add_argument("--mes", help="evalúa un mes histórico (AAAA-MM) en lugar del último")
    args = ap.parse_args()

    cn = conectar()
    cur = cn.cursor()
    series, meses = ventas_mensuales(cur)
    if args.mes:
        meses = [m for m in meses if m <= args.mes]
    if len(meses) < MESES_REFERENCIA + 1:
        print("No hay suficientes meses de datos para evaluar.")
        return
    candidatas = list(reglas_ventas(series, meses, args.umbral))
    if not args.mes:
        candidatas += list(reglas_modelo(cur, series, meses, args.umbral))
    if args.simular:
        candidatas.append(simulada(series, meses, args.umbral))
    nuevas = sum(1 for a in candidatas if crear_alerta(cur, a))
    cn.commit()
    ok, mal = enviar_pendientes(cn)
    print(f"Umbral {args.umbral:g}% | mes evaluado {meses[-1]} | candidatas {len(candidatas)} | nuevas {nuevas} | "
          f"duplicadas omitidas {len(candidatas) - nuevas} | correos enviados {ok} | fallidos {mal}")


if __name__ == "__main__":
    main()