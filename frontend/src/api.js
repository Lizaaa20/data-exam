const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const getToken = () => sessionStorage.getItem('token');
export const setToken = (t) =>
  t ? sessionStorage.setItem('token', t) : sessionStorage.removeItem('token');

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = 'GET', params, body } = {}) {
  const url = new URL(BASE + path);
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  });
  const headers = {};
  const t = getToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  if (body) headers['Content-Type'] = 'application/json';

  let res;
  try {
    res = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError(0, 'No hay conexión con la API');
  }
  if (!res.ok) {
    let msg = 'Error al consultar los datos';
    try {
      const j = await res.json();
      if (typeof j.detail === 'string') msg = j.detail;
    } catch {
      /* sin cuerpo JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export const api = {
  login: (usuario, clave) => request('/auth/login', { method: 'POST', body: { usuario, clave } }),
  kpis: (f) => request('/kpis', { params: f }),
  tendencia: (f, granularidad) => request('/ventas/tendencia', { params: { ...f, granularidad } }),
  porCategoria: (f) => request('/ventas/por-categoria', { params: f }),
  porEstado: (f) => request('/ventas/por-estado', { params: f }),
  topProductos: (f) => request('/ventas/top-productos', { params: f }),
  topClientes: (f) => request('/ventas/top-clientes', { params: f }),
  detalle: (f, pagina, tamano) => request('/ventas/detalle', { params: { ...f, pagina, tamano } }),
  filtros: () => request('/meta/filtros'),
  actualizacion: () => request('/meta/ultima-actualizacion'),
};