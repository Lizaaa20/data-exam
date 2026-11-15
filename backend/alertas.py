import os

import pyodbc
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

ESTADOS = ("NUEVA", "ATENDIDA", "DESCARTADA", "RESUELTA")


class CambioEstado(BaseModel):
    estado: str


def _cambiar_estado(alerta_id: int, estado: str) -> int:
    cn = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.getenv('MSSQL_HOST')},{os.getenv('MSSQL_PORT')};DATABASE=WWI_DW;"
        f"UID={os.getenv('MSSQL_API_USER')};PWD={os.getenv('MSSQL_API_PASSWORD')};"
        "TrustServerCertificate=yes;",
        timeout=30,
    )
    try:
        cur = cn.cursor()
        cur.execute("EXEC dw.usp_set_alert_status ?, ?", alerta_id, estado)
        filas = cur.fetchone()[0]
        cn.commit()
        return filas
    finally:
        cn.close()


def crear_router(consulta, usuario_dep):
    router = APIRouter(dependencies=[Depends(usuario_dep)])

    @router.get("/alertas", tags=["alertas"])
    def listar(estado: str | None = Query(None), limite: int = Query(50, ge=1, le=200)):
        donde, params = "", []
        if estado:
            if estado not in ESTADOS:
                raise HTTPException(422, "Estado no válido")
            donde, params = "WHERE Status = ?", [estado]
        alertas = consulta(
            "SELECT TOP (?) AlertId, CreatedAt, AlertType, Severity, Entity, ChangePct, Source, Status "
            "FROM dw.Alert " + donde + " ORDER BY CreatedAt DESC, AlertId DESC",
            [limite] + params,
        )
        resumen = consulta("SELECT Status AS estado, COUNT(*) AS n FROM dw.Alert GROUP BY Status")
        return {"alertas": alertas, "resumen": resumen}

    @router.get("/alertas/{alerta_id}", tags=["alertas"])
    def detalle(alerta_id: int):
        a = consulta("SELECT * FROM dw.Alert WHERE AlertId = ?", [alerta_id])
        if not a:
            raise HTTPException(404, "Alerta no encontrada")
        entregas = consulta(
            "SELECT Channel, Status, Attempts, LastError, LastAttemptAt, DeliveredAt "
            "FROM dw.AlertDelivery WHERE AlertId = ? ORDER BY Channel", [alerta_id])
        return {"alerta": a[0], "entregas": entregas}

    @router.post("/alertas/{alerta_id}/estado", tags=["alertas"])
    def cambiar(alerta_id: int, c: CambioEstado):
        if c.estado not in ESTADOS:
            raise HTTPException(422, "Estado no válido")
        if _cambiar_estado(alerta_id, c.estado) == 0:
            raise HTTPException(404, "Alerta no encontrada")
        return {"alerta_id": alerta_id, "estado": c.estado}

    return router