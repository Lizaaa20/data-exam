import json
import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import pyodbc
from dotenv import load_dotenv
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import ParameterGrid
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

load_dotenv()

HORIZONTES = [1, 2, 3]   # meses hacia adelante
MESES_PRUEBA = 6         # últimos meses reservados para la evaluación final
MIN_MESES_HISTORIA = 24  # categorías con menos meses con ventas no se modelan
SEMILLA = 42
VERSION = datetime.now().strftime("v%Y%m%d_%H%M")
AQUI = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(AQUI, "models"), exist_ok=True)
os.makedirs(os.path.join(AQUI, "resultados"), exist_ok=True)

REJILLAS = {
    "ridge": list(ParameterGrid({"alpha": [0.1, 1.0, 10.0, 100.0]})),
    "gradient_boosting": list(
        ParameterGrid({"n_estimators": [100, 200], "max_depth": [2, 3], "learning_rate": [0.05, 0.1]})
    ),
}
BASELINES = ["naive", "estacional"]


# ---------- Datos ----------
def conectar():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.getenv('MSSQL_HOST')},{os.getenv('MSSQL_PORT')};DATABASE=WWI_DW;"
        f"UID={os.getenv('MSSQL_WRITER_USER')};PWD={os.getenv('MSSQL_WRITER_PASSWORD')};"
        "TrustServerCertificate=yes;"
    )


def cargar_serie(cn) -> pd.DataFrame:
    cur = cn.cursor()
    cur.execute(
        "SELECT d.YearMonth, p.PrimaryCategory, SUM(f.NetSalesAmount) "
        "FROM dw.FactSales f "
        "JOIN dw.DimDate d ON d.DateKey = f.DateKey "
        "JOIN dw.DimProduct p ON p.ProductKey = f.ProductKey "
        "WHERE p.ProductKey <> -1 "
        "GROUP BY d.YearMonth, p.PrimaryCategory"
    )
    df = pd.DataFrame([tuple(r) for r in cur.fetchall()], columns=["mes", "categoria", "ventas"])
    df["mes"] = df["mes"].str.strip()
    df["ventas"] = df["ventas"].astype(float)
    serie = df.pivot(index="mes", columns="categoria", values="ventas").sort_index()
    serie.index = pd.PeriodIndex(serie.index, freq="M")
    completo = pd.period_range(serie.index.min(), serie.index.max(), freq="M")
    return serie.reindex(completo).fillna(0.0)


# ---------- Variables (solo usan meses <= t, el último mes conocido) ----------
def fila(v, meses, cat, cats, t, h):
    mes_destino = meses[t] + h
    ang = 2 * np.pi * (mes_destino.month - 1) / 12
    f = {
        "categoria": cat,
        "t": t,
        "h": h,
        "destino": t + h,
        "mes_destino": str(mes_destino),
        "l0": np.log1p(v[t]),
        "l1": np.log1p(v[t - 1]),
        "l2": np.log1p(v[t - 2]),
        "roll3": np.log1p(v[t - 2 : t + 1].mean()),
        "estac": np.log1p(v[t + h - 12]),   # mismo mes del año anterior
        "mes_sin": np.sin(ang),
        "mes_cos": np.cos(ang),
        "horizonte": float(h),
        "naive_real": v[t],
        "estacional_real": v[t + h - 12],
    }
    for c in cats:
        f[f"cat_{c}"] = 1.0 if c == cat else 0.0
    return f


def construir(serie, solo_origen_final=False) -> pd.DataFrame:
    cats, meses, T = list(serie.columns), serie.index, len(serie)
    filas = []
    for cat in cats:
        v = serie[cat].to_numpy(dtype=float)
        for h in HORIZONTES:
            origenes = [T - 1] if solo_origen_final else range(11, T - h)
            for t in origenes:
                f = fila(v, meses, cat, cats, t, h)
                if not solo_origen_final:
                    f["y_real"] = v[t + h]
                    f["y"] = np.log1p(v[t + h])
                filas.append(f)
    return pd.DataFrame(filas)


def columnas(cats):
    return ["l0", "l1", "l2", "roll3", "estac", "mes_sin", "mes_cos", "horizonte"] + [f"cat_{c}" for c in cats]


# ---------- Modelos y métricas ----------
def crear_modelo(nombre, params):
    if nombre == "ridge":
        return make_pipeline(StandardScaler(), Ridge(**params))
    return GradientBoostingRegressor(random_state=SEMILLA, **params)


def predecir(nombre, modelo, df, cols):
    if nombre == "naive":
        return df["naive_real"].to_numpy()
    if nombre == "estacional":
        return df["estacional_real"].to_numpy()
    return np.clip(np.expm1(modelo.predict(df[cols])), 0, None)


def metricas(real, pred):
    err = pred - real
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "smape": float(np.mean(2 * np.abs(err) / (np.abs(real) + np.abs(pred) + 1e-9)) * 100),
        "sesgo_pct": float(err.sum() / real.sum() * 100),
    }


def cv_mae(nombre, params, train, cols, folds):
    """Validación hacia adelante: siempre se entrena con el pasado y se valida con meses posteriores."""
    maes = []
    for ini, fin in folds:
        tr = train[train["destino"] < ini]
        va = train[(train["destino"] >= ini) & (train["destino"] < fin)]
        modelo = None if nombre in BASELINES else crear_modelo(nombre, params).fit(tr[cols], tr["y"])
        maes.append(metricas(va["y_real"].to_numpy(), predecir(nombre, modelo, va, cols))["mae"])
    return float(np.mean(maes))


def main():
    cn = conectar()
    serie = cargar_serie(cn)
    excluidas = [c for c in serie.columns if (serie[c] > 0).sum() < MIN_MESES_HISTORIA]
    serie = serie.drop(columns=excluidas)
    print(f"Categorías excluidas por historia insuficiente (< {MIN_MESES_HISTORIA} meses con ventas): {excluidas}")
    T, cats = len(serie), list(serie.columns)
    print(f"Serie: {T} meses ({serie.index[0]} a {serie.index[-1]}), {len(cats)} categorías")

    filas = construir(serie)
    cols = columnas(cats)
    corte = T - MESES_PRUEBA                      # índice del primer mes de prueba
    train = filas[filas["destino"] < corte].reset_index(drop=True)
    test = filas[filas["destino"] >= corte].reset_index(drop=True)
    rango_train = f"{serie.index[0]} a {serie.index[corte - 1]}"
    rango_test = f"{serie.index[corte]} a {serie.index[-1]}"
    print(f"Entrenamiento: {rango_train} ({len(train)} filas) | Prueba: {rango_test} ({len(test)} filas)")

    # 1) Elegir hiperparámetros y modelo con validación dentro del entrenamiento (sin tocar la prueba)
    folds = [(corte - 12, corte - 6), (corte - 6, corte)]
    cv_tabla, mejores = [], {}
    for nombre, rejilla in REJILLAS.items():
        res = [(cv_mae(nombre, p, train, cols, folds), p) for p in rejilla]
        score, p = min(res, key=lambda x: x[0])
        mejores[nombre] = p
        cv_tabla.append({"modelo": nombre, "params": json.dumps(p), "cv_mae": score})
    for b in BASELINES:
        cv_tabla.append({"modelo": b, "params": "{}", "cv_mae": cv_mae(b, {}, train, cols, folds)})
    cv_df = pd.DataFrame(cv_tabla).sort_values("cv_mae")
    seleccionado = cv_df.iloc[0]["modelo"]
    print("\nValidación cruzada (MAE, menor es mejor):\n", cv_df.to_string(index=False))
    print("Seleccionado por validación:", seleccionado)

    # 2) Evaluación final en la prueba (datos que no se usaron para decidir nada)
    resultados = []
    for nombre in BASELINES + list(REJILLAS):
        modelo = crear_modelo(nombre, mejores[nombre]).fit(train[cols], train["y"]) if nombre in REJILLAS else None
        pred = predecir(nombre, modelo, test, cols)
        for h in [None] + HORIZONTES:
            mask = np.ones(len(test), dtype=bool) if h is None else (test["h"] == h).to_numpy()
            m = metricas(test["y_real"].to_numpy()[mask], pred[mask])
            resultados.append({"modelo": nombre, "horizonte": "todos" if h is None else h, **m, "filas": int(mask.sum())})
    res_df = pd.DataFrame(resultados)
    print("\nEvaluación en prueba (todos los horizontes):\n",
          res_df[res_df["horizonte"] == "todos"].drop(columns="horizonte").round(2).to_string(index=False))


  # Diagnóstico de sesgo por categoría en la prueba (error acumulado / ventas reales, en %)
    for nombre in ["estacional", "ridge", "gradient_boosting"]:
        modelo_d = crear_modelo(nombre, mejores[nombre]).fit(train[cols], train["y"]) if nombre in REJILLAS else None
        tt = test.assign(pred=predecir(nombre, modelo_d, test, cols))
        g = tt.groupby("categoria")
        sesgo_cat = ((g["pred"].sum() - g["y_real"].sum()) / g["y_real"].sum() * 100).round(1)
        print(f"\nSesgo % por categoría en prueba ({nombre}):\n", sesgo_cat.to_string())



    # 3) Reentrenar el seleccionado con todos los datos y pronosticar desde el último mes
    
    modelo_final = None
    if seleccionado in REJILLAS:
        modelo_final = crear_modelo(seleccionado, mejores[seleccionado]).fit(filas[cols], filas["y"])
    futuro = construir(serie, solo_origen_final=True)
    futuro["pred"] = predecir(seleccionado, modelo_final, futuro, cols)
    print("\nPronóstico:\n", futuro[["categoria", "mes_destino", "h", "pred"]].round(0).to_string(index=False))

    # 4) Guardar artefactos y resultados
    params = mejores.get(seleccionado, {})
    if modelo_final is not None:
        joblib.dump({"modelo": modelo_final, "columnas": cols, "categorias": cats, "version": VERSION},
                    os.path.join(AQUI, "models", f"modelo_{VERSION}.joblib"))
    meta = {"version": VERSION, "modelo": seleccionado, "params": params, "entrenamiento": rango_train,
            "prueba": rango_test, "horizontes": HORIZONTES, "variables": cols,
            "cv": cv_df.to_dict("records"), "prueba_resultados": res_df.to_dict("records")}
    with open(os.path.join(AQUI, "models", f"modelo_{VERSION}.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    cv_df.to_csv(os.path.join(AQUI, "resultados", "cv.csv"), index=False)
    res_df.to_csv(os.path.join(AQUI, "resultados", "prueba.csv"), index=False)
    futuro[["categoria", "mes_destino", "h", "pred"]].to_csv(
        os.path.join(AQUI, "resultados", "pronostico.csv"), index=False)

    sel = res_df[(res_df["modelo"] == seleccionado) & (res_df["horizonte"] == "todos")].iloc[0]
    bases = res_df[(res_df["modelo"].isin(BASELINES)) & (res_df["horizonte"] == "todos")]
    base = bases.sort_values("mae").iloc[0]
    cur = cn.cursor()
    cur.execute(
        "INSERT dw.ModelRun (ModelVersion, ModelName, TrainedAt, TrainRange, TestRange, Params, MaeTest, "
        "RmseTest, SmapeTest, BaselineName, BaselineMaeTest) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        VERSION, seleccionado, datetime.now().replace(microsecond=0), rango_train, rango_test,
        json.dumps(params), round(sel["mae"], 2), round(sel["rmse"], 2), round(sel["smape"], 2),
        base["modelo"], round(base["mae"], 2),
    )
    cur.fast_executemany = True
    cur.executemany(
        "INSERT dw.PredictedSales (ModelVersion, PredictionDate, Category, TargetMonth, HorizonMonths, "
        "PredictedSales) VALUES (?,?,?,?,?,?)",
        [(VERSION, datetime.now().date(), r.categoria, r.mes_destino, int(r.h), round(float(r.pred), 2))
         for r in futuro.itertuples()],
    )
    cn.commit()
    print(f"\nListo. Versión {VERSION} guardada en dw.ModelRun y dw.PredictedSales")


if __name__ == "__main__":
    main()