# data-exam
Plataforma de ingeniería de datos y analítica inteligente: ETL, Data Warehouse, dashboard, ML, IA generativa y alertas (SQL Server + Python).

# Plataforma de Ingeniería de Datos y Analítica Inteligente

Proyecto académico (CEUTEC). Convierte datos operacionales de **WideWorldImporters** (SQL Server) en un Data Warehouse
dimensional y habilita análisis descriptivo, predicción, un asistente de IA generativa y alertas.

- **Equipo:** _[completar]_ · **Docente:** _[completar]_
- **Proceso de negocio:** ventas. **Grano:** una fila por línea de factura (`Sales.InvoiceLines`).

Flujo: `WWI_Source` → `raw` → `clean` (calidad y cuarentena) → `ready` → `WWI_DW` (esquema estrella) → API → dashboard,
modelo de ML, asistente y alertas. Diagramas en [`documentation/diagramas.md`](documentation/diagramas.md).

## Requisitos

- Windows 11, **12 GB de RAM** (con menos, usar una API en la nube para el asistente)
- SQL Server 2022 Developer + SSMS, con **TCP/IP en el puerto 1433** y **autenticación mixta**
- Docker Desktop (WSL2) y Git
- `WideWorldImporters-Standard.bak` (release `wide-world-importers-v1.0` de `microsoft/sql-server-samples`),
  copiado a la carpeta `Backup` de la instancia

## Estructura

```
database/      scripts SQL (orden numérico)      etl/              extracción, limpieza, carga y orquestación
backend/       API FastAPI                       frontend/         dashboard React + ECharts
machine-learning/  entrenamiento y modelos       notifications/    evaluación de alertas
tests/         pruebas del asistente             deployment/       Dockerfile y docker-compose.yml
documentation/ diagramas, perfiles, pruebas      .env.example      variables (sin valores reales)
```

## Puesta en marcha

Todos los comandos `docker compose` se ejecutan **desde la carpeta `deployment`**.

**1. Configuración.** Copia `.env.example` a `.env` y completa los valores (nunca se sube al repo). Los usuarios
`etl_reader`, `etl_writer` y `api_reader` se crean en el paso 2 con las contraseñas que pongas aquí.

**2. SQL Server** (SSMS, como `sa`, en este orden):

| Script | Qué hace |
|---|---|
| `00_ajustes_servidor.sql` | Tope de memoria de SQL Server (3 GB) |
| `01_restaurar_wwi.sql` | Restaura `WWI_Source` y crea `WWI_Staging` y `WWI_DW` |
| `02_usuarios.sql` | Logins con mínimo privilegio (reemplaza `<CLAVE_READER>` y `<CLAVE_WRITER>`) |
| `03_verificar_fuente.sql` | Debe dar 70,510 facturas y 228,265 líneas |
| `03b_desactivar_rls.sql` | Desactiva la seguridad por fila de `Sales.Customers` (ambiente local) |
| `04_esquemas_staging.sql` | Esquemas `raw`, `clean`, `ready`, `audit`, `quarantine` y `dw` |
| `05_dw_modelo.sql` | Dimensiones y hecho (borra y recrea esas 5 tablas) |
| `06_auditoria_cuarentena.sql` | Auditoría, watermarks y catálogo de reglas de calidad |
| `14_usuario_api.sql` | Usuario de solo lectura de la API (reemplaza `<CLAVE_API>`) |
| `16_ml_tablas.sql`, `19_alertas.sql` | Tablas de modelo y de alertas |

**3. Capas `raw`, `clean` y DW** (primera carga):

```powershell
cd deployment
docker compose build etl
docker compose run --rm etl python etl/carga_inicial_raw.py
```

Luego en SSMS: `07_clean_ventas.sql`, `10_ready_vistas.sql` y `11_cargar_dw.sql`. Después:

```powershell
docker compose run --rm etl python etl/limpiar_ventas.py
docker compose run --rm etl python etl/cargar_dw.py
```

Verifica con `15_validar_kpis.sql` y la consulta de reconciliación de `documentation`.

**4. Modelo de ML:**

```powershell
docker compose run --rm etl python machine-learning/entrenar.py
```

**5. Servicios:**

```powershell
docker compose up -d api web mailpit ollama
docker compose exec ollama ollama pull qwen2.5:3b
```

| Servicio | URL |
|---|---|
| Dashboard | http://localhost:5173 (usuario y clave de `API_USER` y `API_PASSWORD`) |
| API y documentación | http://localhost:8000/docs |
| Correos de prueba | http://localhost:8025 |

Con 12 GB de RAM, limita WSL en `C:\Users\<usuario>\.wslconfig` (`[wsl2]`, `memory=5GB`, `processors=3`) y ejecuta
`wsl --shutdown`. Cierra el navegador y otras aplicaciones al usar el asistente de IA.

## Operación

- **Pipeline completo** (carga incremental → limpieza → DW → alertas, con reintento por etapa):
  `docker compose run --rm etl python etl/pipeline.py`
- **Recuperación:** las cargas son idempotentes y el watermark solo avanza si la etapa termina bien, así que
  una ejecución fallida se reintenta con el mismo comando. El historial queda en `WWI_Staging.audit.etl_run`.
- **Alertas:** `python notifications/evaluar_alertas.py [--umbral 15] [--mes AAAA-MM] [--simular]`
  (`--simular` crea una alerta marcada como simulación).
- **Demostración de la carga incremental:** `12_simular_cambios_fuente.sql` y luego el pipeline.
  `08_lote_prueba_sucio.sql` y `09_limpiar_lote_prueba.sql` demuestran la cuarentena con datos defectuosos.

## Pruebas y evidencias

- Reconciliación fuente, staging y DW; KPIs de la API contra SQL independiente: `15_validar_kpis.sql`
- Asistente (12 preguntas): `python tests/probar_asistente.py` y `18_validar_asistente.sql`; resultados en
  `documentation/pruebas_asistente.md`
- Capturas en `documentation/evidencias/`

## Limitaciones conocidas

- Los datos van de **2013-01 a 2016-05**: es un histórico, no un flujo en producción. Sin descuentos ni devoluciones.
- La categoría de un producto es la de mayor `StockGroupID`; Mugs, T-Shirts y Airline Novelties no aparecen como categoría.
- ML: 41 meses por categoría, prueba de 6 meses; Novelty Items se excluye (menos de 24 meses de historia).
- El asistente usa un modelo local de 3B: los rankings, comparaciones y tendencias los calcula el código; la
  interpretación de IA solo se verifica en cifras y signos, no en comparaciones.
- Las alertas se evalúan por corrida del pipeline (no es tiempo real). Las simuladas están marcadas como `SIMULACION`.
- No se detectan eliminaciones en la fuente. La política RLS de WWI se desactiva solo en el ambiente local.

## Seguridad

Contraseñas solo en `.env` (excluido por `.gitignore`); mínimo privilegio por usuario (`etl_reader` solo lectura,
`etl_writer` en staging y DW, `api_reader` solo lectura); el navegador nunca toca SQL Server; consultas parametrizadas;
el asistente no ejecuta SQL libre y con Ollama ningún dato sale del equipo.

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `no configuration file provided` | Ejecutar `docker compose` desde `deployment` |
| `Login failed ... (18456)` en la API | La clave del `.env` no coincide con la de SQL Server; recrear con `--force-recreate` |
| Error 802 de memoria o base `SUSPECT` | Aplicar los topes de memoria; usar el backup `Standard` en lugar del `Full` |
| `Sales.Customers` devuelve 0 filas | Ejecutar `03b_desactivar_rls.sql` |
| Librerías de Python bloqueadas en Windows | Por eso el ETL corre en Docker (Control Inteligente de Aplicaciones) |
