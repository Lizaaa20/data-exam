import { useState } from 'react';
import { api, setToken } from './api';

export default function Login({ onEntrar }) {
  const [usuario, setUsuario] = useState('');
  const [clave, setClave] = useState('');
  const [error, setError] = useState('');
  const [enviando, setEnviando] = useState(false);

  async function enviar(e) {
    e.preventDefault();
    setError('');
    setEnviando(true);
    try {
      const r = await api.login(usuario, clave);
      setToken(r.token);
      onEntrar();
    } catch (err) {
      setError(err.status === 401 ? 'Usuario o clave incorrectos' : err.message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="centro">
      <form className="login" onSubmit={enviar}>
        <h1>Analítica de ventas</h1>
        <label>
          Usuario
          <input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" required />
        </label>
        <label>
          Clave
          <input
            type="password"
            value={clave}
            onChange={(e) => setClave(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={enviando}>
          {enviando ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  );
}