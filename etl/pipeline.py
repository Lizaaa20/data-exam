import os
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ETAPAS = ["etl/carga_incremental.py", "etl/limpiar_ventas.py", "etl/cargar_dw.py",
          "notifications/evaluar_alertas.py"]
REINTENTOS = 2

for etapa in ETAPAS:
    for intento in range(1, REINTENTOS + 1):
        print(f"\n=== {etapa} (intento {intento}/{REINTENTOS}) ===", flush=True)
        r = subprocess.run([sys.executable, os.path.join(RAIZ, etapa)], cwd=RAIZ)
        if r.returncode == 0:
            break
        time.sleep(5)
    else:
        print(f"Pipeline detenido: {etapa} falló. Revisa audit.etl_run.")
        sys.exit(1)

print("\nPipeline completo.")