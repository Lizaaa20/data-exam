import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import Chart from './Chart';
import { compacto, fechaHora, money } from './format';

export default function Prediccion() {
  const [d, setD] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.prediccion().then(setD).catch((e) => setError(e.message));
  }, []);

  const opcion = useMemo(() => {
    if (!d || !d.modelo) return null;
    const hist = d.historico.slice(-24);
    const mesesPred = [...new Set(d.pronostico.map((p) => p.mes))];
    const meses = [...hist.map((h) => h.mes), ...mesesPred];
    const total = {};
    d.pronostico.forEach((p) => {
      total[p.mes] = (total[p.mes] || 0) + p.ventas_predichas;
    });
    return {
      tooltip: { trigger: 'axis', valueFormatter: (v) => money(v) },
      legend: { data: ['Histórico (real)', 'Pronóstico (modelo)'] },
      grid: { left: 70, right: 20, top: 40, bottom: 40 },
      xAxis: { type: 'category', data: meses },
      yAxis: { type: 'value', axisLabel: { formatter: compacto } },
      series: [
        {
          name: 'Histórico (real)',
          type: 'line',
          data: meses.map((m) => hist.find((h) => h.mes === m)?.ventas_netas ?? null),
        },
        {
          name: 'Pronóstico (modelo)',
          type: 'line',
          data: meses.map((m) => total[m] ?? null),
          lineStyle: { type: 'dashed' },
          itemStyle: { color: '#e07b00' },
        },
      ],
    };
  }, [d]);

  if (error) {
    return (
      <section className="tarjeta">
        <h3>Pronóstico de ventas</h3>
        <p className="vacio">{error}</p>
      </section>
    );
  }
  if (!d) return null;
  if (!d.modelo) {
    return (
      <section className="tarjeta">
        <h3>Pronóstico de ventas</h3>
        <p className="vacio">Todavía no hay un modelo entrenado</p>
      </section>
    );
  }

  const m = d.modelo;
  const cats = [...new Set(d.pronostico.map((p) => p.categoria))];
  const mesesPred = [...new Set(d.pronostico.map((p) => p.mes))];
  const valor = (c, mes) => d.pronostico.find((p) => p.categoria === c && p.mes === mes)?.ventas_predichas;

  return (
    <section className="tarjeta">
      <h3>Pronóstico de ventas: PREDICCIÓN, no son datos históricos</h3>
      <p className="nota">
        Modelo {m.ModelName}, versión {m.ModelVersion}, entrenado el {fechaHora(m.TrainedAt)}. Datos de
        entrenamiento: {m.TrainRange}; prueba: {m.TestRange}. Error medio (MAE) en prueba:{' '}
        {money(m.MaeTest)} frente a {money(m.BaselineMaeTest)} de la mejor línea base ({m.BaselineName});
        sMAPE {m.SmapeTest}%. Horizonte de 3 meses desde el último mes con datos. No incluye las
        categorías con menos de 24 meses de historia (por ejemplo, Novelty Items). Es una estimación
        con incertidumbre alta, por la poca historia disponible.
      </p>
      <Chart option={opcion} />
      <div className="tabla">
        <table>
          <thead>
            <tr>
              <th>Categoría</th>
              {mesesPred.map((mes) => (
                <th key={mes} className="der">
                  {mes}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cats.map((c) => (
              <tr key={c}>
                <td>{c}</td>
                {mesesPred.map((mes) => (
                  <td key={mes} className="der">
                    {money(valor(c, mes))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}