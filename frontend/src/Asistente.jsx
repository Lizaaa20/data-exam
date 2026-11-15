import { useState } from 'react';
import { api } from './api';
import { fechaHora } from './format';

const EJEMPLOS = [
  '¿Cuáles fueron las ventas del último año?',
  '¿Qué categorías tuvieron mayor crecimiento?',
  '¿Qué estados presentan una disminución relevante?',
  'Resume los principales cambios respecto al período anterior',
];

export default function Asistente() {
  const [pregunta, setPregunta] = useState('');
  const [cargando, setCargando] = useState(false);
  const [r, setR] = useState(null);
  const [error, setError] = useState('');

  async function enviar(texto) {
    const q = (texto ?? pregunta).trim();
    if (q.length < 3) return;
    setPregunta(q);
    setCargando(true);
    setError('');
    setR(null);
    try {
      setR(await api.preguntar(q));
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  }

  return (
    <section className="tarjeta">
      <h3>Asistente analítico (IA generativa)</h3>
      <p className="nota">
        Responde solo con datos del Data Warehouse. La redacción la genera un modelo de lenguaje local y sus
        cifras se verifican contra los datos consultados.
      </p>
      <form
        className="chat"
        onSubmit={(e) => {
          e.preventDefault();
          enviar();
        }}
      >
        <input
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          maxLength={300}
          placeholder="Escribe tu pregunta sobre las ventas"
        />
        <button type="submit" disabled={cargando}>
          {cargando ? 'Consultando…' : 'Preguntar'}
        </button>
      </form>
      <div className="chips">
        {EJEMPLOS.map((e) => (
          <button key={e} className="chip" disabled={cargando} onClick={() => enviar(e)}>
            {e}
          </button>
        ))}
      </div>
      {cargando && <p className="nota">Consultando los datos y redactando; puede tardar hasta un minuto.</p>}
      {error && <div className="aviso">{error}</div>}
      {r && (
        <div className="respuesta">
          <p style={{ whiteSpace: 'pre-wrap' }}>{r.respuesta}</p>
          <p className="nota">
            Fuente: {r.fuente} · datos actualizados {fechaHora(r.actualizado)} · tipo: {r.tipo}
            {r.periodo ? ` · período ${r.periodo}` : ''} ·{' '}
            {r.generada_por_ia ? 'texto generado por IA, cifras verificadas' : 'sin redacción de IA'}
            {r.herramienta ? ` · consulta: ${r.herramienta}` : ''}
          </p>
          {r.aviso && <p className="nota">{r.aviso}</p>}
          {r.datos_texto && (
            <details>
              <summary>Ver los datos que respaldan la respuesta</summary>
              <pre>{r.datos_texto}</pre>
            </details>
          )}
        </div>
      )}
    </section>
  );
}