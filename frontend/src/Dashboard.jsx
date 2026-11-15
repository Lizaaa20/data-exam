import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, ApiError } from './api';
import Chart from './Chart';
import { compacto, fechaHora, inicioUltimoAnio, money, num, pct } from './format';
import Prediccion from './Prediccion';
import Alertas from './Alertas';
import Asistente from "./Asistente.jsx";

const KPIS = [
  { key: 'ventas_netas', label: 'Ventas netas', fmt: (v) => money(v) },
  { key: 'utilidad', label: 'Utilidad', fmt: (v) => money(v) },
  { key: 'margen_pct', label: 'Margen', fmt: (v) => pct(v), unidad: ' pp' },
  { key: 'unidades', label: 'Unidades vendidas', fmt: (v) => num(v) },
  { key: 'facturas', label: 'Facturas', fmt: (v) => num(v) },
  { key: 'ticket_promedio', label: 'Ticket promedio', fmt: (v) => money(v, 2) },
];

function Variacion({ valor, unidad = '%' }) {
  if (valor === null || valor === undefined) return <span className="var neutro">—</span>;
  const clase = valor > 0 ? 'pos' : valor < 0 ? 'neg' : 'neutro';
  const signo = valor > 0 ? '▲' : valor < 0 ? '▼' : '■';
  return (
    <span className={`var ${clase}`}>
      {signo} {Math.abs(valor).toFixed(1)}
      {unidad}
    </span>
  );
}

function Tarjeta({ titulo, vacio, children }) {
  return (
    <section className="tarjeta">
      <h3>{titulo}</h3>
      {vacio ? <p className="vacio">Sin datos para estos filtros</p> : children}
    </section>
  );
}

function barraH(filas, nombre, valor) {
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v) => money(v) },
    grid: { left: 150, right: 20, top: 10, bottom: 20 },
    xAxis: { type: 'value', axisLabel: { formatter: compacto } },
    yAxis: {
      type: 'category',
      inverse: true,
      data: filas.map((f) => f[nombre]),
      axisLabel: { width: 140, overflow: 'truncate' },
    },
    series: [{ type: 'bar', data: filas.map((f) => f[valor]) }],
  };
}

export default function Dashboard({ onSalir }) {
  const [meta, setMeta] = useState(null);
  const [filtros, setFiltros] = useState(null);
  const [gran, setGran] = useState('mes');
  const [comparar, setComparar] = useState('periodo_anterior');
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');
  const [pagina, setPagina] = useState(1);
  const [detalle, setDetalle] = useState(null);
  const [actualizacion, setActualizacion] = useState(null);

  const manejar = useCallback(
    (e) => {
      if (e instanceof ApiError && e.status === 401) onSalir();
      else setError(e.message || 'Error inesperado');
    },
    [onSalir],
  );

  const cambiar = useCallback((c) => setFiltros((f) => ({ ...f, ...c })), []);
  const clickCategoria = useCallback((nombre) => cambiar({ categoria: nombre }), [cambiar]);
  const clickEstado = useCallback((nombre) => cambiar({ estado: nombre }), [cambiar]);

  // Metadatos iniciales (rango de fechas, categorías, estados, última carga)
  useEffect(() => {
    Promise.all([api.filtros(), api.actualizacion()])
      .then(([m, a]) => {
        setMeta(m);
        setActualizacion(a.ultima_carga);
        setFiltros({
          desde: inicioUltimoAnio(m.rango_fechas.hasta, m.rango_fechas.desde),
          hasta: m.rango_fechas.hasta,
          categoria: '',
          estado: '',
        });
      })
      .catch(manejar);
  }, [manejar]);

  // Panel principal
  useEffect(() => {
    if (!filtros) return undefined;
    let vigente = true;
    setCargando(true);
    setError('');
    Promise.all([
      api.kpis(filtros),
      api.tendencia(filtros, gran),
      api.porCategoria(filtros),
      api.porEstado(filtros),
      api.topProductos(filtros),
      api.topClientes(filtros),
    ])
      .then(([kpis, tendencia, categorias, estados, productos, clientes]) => {
        if (vigente) setDatos({ kpis, tendencia, categorias, estados, productos, clientes });
      })
      .catch((e) => vigente && manejar(e))
      .finally(() => vigente && setCargando(false));
    return () => {
      vigente = false;
    };
  }, [filtros, gran, manejar]);

  // Tabla de detalle
  useEffect(() => {
    setPagina(1);
  }, [filtros]);

  useEffect(() => {
    if (!filtros) return undefined;
    let vigente = true;
    api
      .detalle(filtros, pagina, 15)
      .then((d) => vigente && setDetalle(d))
      .catch((e) => vigente && manejar(e));
    return () => {
      vigente = false;
    };
  }, [filtros, pagina, manejar]);

  const opciones = useMemo(() => {
    if (!datos) return null;
    return {
      tendencia: {
        tooltip: { trigger: 'axis', valueFormatter: (v) => money(v) },
        legend: { data: ['Ventas netas', 'Utilidad'] },
        grid: { left: 70, right: 20, top: 40, bottom: 40 },
        xAxis: { type: 'category', data: datos.tendencia.map((r) => r.periodo) },
        yAxis: { type: 'value', axisLabel: { formatter: compacto } },
        series: [
          { name: 'Ventas netas', type: 'line', smooth: true, data: datos.tendencia.map((r) => r.ventas_netas) },
          { name: 'Utilidad', type: 'line', smooth: true, data: datos.tendencia.map((r) => r.utilidad) },
        ],
      },
      categorias: barraH(datos.categorias, 'categoria', 'ventas_netas'),
      estados: barraH(datos.estados, 'estado', 'ventas_netas'),
      productos: barraH(datos.productos, 'producto', 'ventas_netas'),
      clientes: barraH(datos.clientes, 'cliente', 'ventas_netas'),
    };
  }, [datos]);

  if (!filtros) {
    return (
      <div className="centro">
        {error ? (
          <div className="aviso">
            {error} <button onClick={onSalir}>Volver al login</button>
          </div>
        ) : (
          'Cargando…'
        )}
      </div>
    );
  }

  const cmp = datos ? datos.kpis[comparar] : null;
  const parcial = Boolean(cmp) && cmp.desde < meta.rango_fechas.desde;
  const sinDatos = datos && datos.kpis.actual.facturas === 0;
  const paginas = detalle ? Math.max(1, Math.ceil(detalle.total / detalle.tamano)) : 1;

  return (
    <div className="app">
      <header className="barra">
        <div>
          <h1>Ventas WideWorldImporters</h1>
          <small>Datos actualizados: {fechaHora(actualizacion)}</small>
        </div>
        <button className="sec" onClick={onSalir}>
          Cerrar sesión
        </button>
      </header>

      <section className="filtros">
        <label>
          Desde
          <input
            type="date"
            value={filtros.desde}
            min={meta.rango_fechas.desde}
            max={meta.rango_fechas.hasta}
            onChange={(e) => e.target.value && cambiar({ desde: e.target.value })}
          />
        </label>
        <label>
          Hasta
          <input
            type="date"
            value={filtros.hasta}
            min={meta.rango_fechas.desde}
            max={meta.rango_fechas.hasta}
            onChange={(e) => e.target.value && cambiar({ hasta: e.target.value })}
          />
        </label>
        <label>
          Categoría
          <select value={filtros.categoria} onChange={(e) => cambiar({ categoria: e.target.value })}>
            <option value="">Todas</option>
            {meta.categorias.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label>
          Estado
          <select value={filtros.estado} onChange={(e) => cambiar({ estado: e.target.value })}>
            <option value="">Todos</option>
            {meta.estados.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Comparar con
          <select value={comparar} onChange={(e) => setComparar(e.target.value)}>
            <option value="periodo_anterior">Período anterior</option>
            <option value="anio_anterior">Mismo período, año anterior</option>
          </select>
        </label>
        <label>
          Tendencia por
          <select value={gran} onChange={(e) => setGran(e.target.value)}>
            <option value="mes">Mes</option>
            <option value="trimestre">Trimestre</option>
            <option value="anio">Año</option>
          </select>
        </label>
      </section>

      <div className="chips">
        {filtros.categoria && (
          <button className="chip" onClick={() => cambiar({ categoria: '' })}>
            Categoría: {filtros.categoria} ✕
          </button>
        )}
        {filtros.estado && (
          <button className="chip" onClick={() => cambiar({ estado: '' })}>
            Estado: {filtros.estado} ✕
          </button>
        )}
      </div>

      {error && (
        <div className="aviso">
          {error} <button onClick={() => setFiltros((f) => ({ ...f }))}>Reintentar</button>
        </div>
      )}
      {sinDatos && <div className="aviso info">No hay ventas en el período y filtros seleccionados.</div>}

      <main className={cargando ? 'cargando' : ''}>
        {datos && (
          <>
            <section className="kpis">
              {KPIS.map((k) => (
                <article className="kpi" key={k.key}>
                  <span className="etiqueta">{k.label}</span>
                  <strong>{k.fmt(datos.kpis.actual[k.key])}</strong>
                  <Variacion valor={cmp.variacion[k.key]} unidad={k.unidad} />
                </article>
              ))}
            </section>
            <p className="nota">
              Variación frente a {cmp.desde} – {cmp.hasta}. El margen se compara en puntos porcentuales (pp).
              {parcial &&
                ' El período de comparación empieza antes del primer dato disponible, por lo que la variación puede no ser comparable.'}
            </p>

            <div className="rejilla">
              <Tarjeta titulo="Tendencia histórica" vacio={!datos.tendencia.length}>
                <Chart option={opciones.tendencia} />
              </Tarjeta>
              <Tarjeta titulo="Ventas por categoría (clic para filtrar)" vacio={!datos.categorias.length}>
                <Chart option={opciones.categorias} onClick={clickCategoria} />
              </Tarjeta>
              <Tarjeta titulo="Ventas por estado, top 15 (clic para filtrar)" vacio={!datos.estados.length}>
                <Chart option={opciones.estados} onClick={clickEstado} altura={420} />
              </Tarjeta>
              <Tarjeta titulo="Top 10 productos" vacio={!datos.productos.length}>
                <Chart option={opciones.productos} />
              </Tarjeta>
              <Tarjeta titulo="Top 10 clientes" vacio={!datos.clientes.length}>
                <Chart option={opciones.clientes} />
              </Tarjeta>
            </div>
          </>
        )}

        <Alertas />
        <Asistente />

        <Prediccion />
        <Tarjeta titulo="Detalle de ventas" vacio={detalle && detalle.total === 0}>
          {detalle && (
            <>
              <div className="tabla">
                <table>
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Factura</th>
                      <th>Cliente</th>
                      <th>Producto</th>
                      <th>Categoría</th>
                      <th>Estado</th>
                      <th className="der">Cant.</th>
                      <th className="der">Ventas</th>
                      <th className="der">Utilidad</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detalle.filas.map((f) => (
                      <tr key={f.linea}>
                        <td>{f.fecha}</td>
                        <td>{f.factura}</td>
                        <td>{f.cliente}</td>
                        <td>{f.producto}</td>
                        <td>{f.categoria}</td>
                        <td>{f.estado}</td>
                        <td className="der">{num(f.cantidad)}</td>
                        <td className="der">{money(f.ventas_netas, 2)}</td>
                        <td className="der">{money(f.utilidad, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="paginacion">
                <button className="sec" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
                  ← Anterior
                </button>
                <span>
                  Página {pagina} de {num(paginas)} · {num(detalle.total)} líneas
                </span>
                <button className="sec" disabled={pagina >= paginas} onClick={() => setPagina((p) => p + 1)}>
                  Siguiente →
                </button>
              </div>
            </>
          )}
        </Tarjeta>
      </main>
    </div>
  );
}