import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { fechaHora, money } from './format';

const ESTADOS = ['NUEVA', 'ATENDIDA', 'DESCARTADA', 'RESUELTA'];
const ORIGEN = { REGLA: 'Regla de negocio', MODELO: 'Modelo (predicción)', SIMULACION: 'SIMULACIÓN' };

export default function Alertas() {
  const [filtro, setFiltro] = useState('');
  const [datos, setDatos] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [error, setError] = useState('');

  const cargar = useCallback(() => {
    api.alertas(filtro).then(setDatos).catch((e) => setError(e.message));
  }, [filtro]);

  useEffect(() => {
    cargar();
    const t = setInterval(cargar, 30000);
    return () => clearInterval(t);
  }, [cargar]);

  const abrir = (id) => api.alerta(id).then(setDetalle).catch((e) => setError(e.message));
  const cambiar = (id, estado) =>
    api
      .cambiarEstado(id, estado)
      .then(() => {
        cargar();
        return abrir(id);
      })
      .catch((e) => setError(e.message));

  if (!datos) return null;
  const cuenta = (e) => datos.resumen.find((r) => r.estado === e)?.n ?? 0;
  const a = detalle?.alerta;

  return (
    <section className="tarjeta">
      <h3>Alertas</h3>
      <p className="nota">
        Se evalúan en cada corrida del pipeline y esta lista se actualiza cada 30 segundos. Nuevas: {cuenta('NUEVA')} ·
        Atendidas: {cuenta('ATENDIDA')} · Descartadas: {cuenta('DESCARTADA')} · Resueltas: {cuenta('RESUELTA')}
      </p>
      <label style={{ maxWidth: 220 }}>
        Estado
        <select value={filtro} onChange={(e) => setFiltro(e.target.value)}>
          <option value="">Todos</option>
          {ESTADOS.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>
      </label>
      {error && <div className="aviso">{error}</div>}
      {datos.alertas.length === 0 ? (
        <p className="vacio">No hay alertas</p>
      ) : (
        <div className="tabla">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Severidad</th>
                <th>Tipo</th>
                <th>Entidad</th>
                <th className="der">Variación</th>
                <th>Origen</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {datos.alertas.map((f) => (
                <tr key={f.AlertId} className="clic" onClick={() => abrir(f.AlertId)}>
                  <td>{fechaHora(f.CreatedAt)}</td>
                  <td>
                    <span className={`sev sev-${f.Severity.toLowerCase()}`}>{f.Severity}</span>
                  </td>
                  <td>{f.AlertType}</td>
                  <td>{f.Entity}</td>
                  <td className="der">{f.ChangePct.toFixed(1)}%</td>
                  <td>{ORIGEN[f.Source] || f.Source}</td>
                  <td>{f.Status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {a && (
        <div className="detalle-alerta">
          <strong>
            Alerta #{a.AlertId} · {a.AlertType} · {ORIGEN[a.Source] || a.Source}
          </strong>
          <p>{a.Explanation}</p>
          <p className="nota">
            Valor observado o predicho: {money(a.ObservedValue, 2)} · referencia: {money(a.ReferenceValue, 2)} (
            {a.ReferencePeriod}) · umbral: -{a.ThresholdPct}%
            {a.ModelVersion ? ` · modelo ${a.ModelVersion}` : ''}
          </p>
          <p className="nota">Acción recomendada: {a.RecommendedAction}</p>
          <p className="nota">
            Entregas:{' '}
            {detalle.entregas
              .map((e) => `${e.Channel} ${e.Status} (${e.Attempts} intento/s${e.LastError ? ', error: ' + e.LastError : ''})`)
              .join(' · ')}
          </p>
          <div className="chips">
            {ESTADOS.filter((e) => e !== a.Status).map((e) => (
              <button key={e} className="chip" onClick={() => cambiar(a.AlertId, e)}>
                Marcar {e.toLowerCase()}
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}