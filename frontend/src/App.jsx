import { useCallback, useState } from 'react';
import Login from './Login';
import Dashboard from './Dashboard';
import { getToken, setToken } from './api';

export default function App() {
  const [autenticado, setAutenticado] = useState(Boolean(getToken()));
  const salir = useCallback(() => {
    setToken(null);
    setAutenticado(false);
  }, []);

  return autenticado ? (
    <Dashboard onSalir={salir} />
  ) : (
    <Login onEntrar={() => setAutenticado(true)} />
  );
}