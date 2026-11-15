import os
import subprocess
import sys
import time

ETAPAS = ["carga_incremental.py", "limpiar_ventas.py", "cargar_dw.py"]
REINTENTOS = 2
aqui = os.path.dirname(os.path.abspath(__file__))

for etapa in ETAPAS:
    for intento in range(1, REINTENTOS + 1):
        print(f"\n=== {etapa} (intento {intento}/{REINTENTOS}) ===", flush=True)
        r = subprocess.run([sys.executable, os.path.join(aqui, etapa)], cwd=os.path.dirname(aqui))
        if r.returncode == 0:
            break
        time.sleep(5)
    else:
        print(f"Pipeline detenido: {etapa} falló. Revisa audit.etl_run.")
        sys.exit(1)

print("\nPipeline completo.")