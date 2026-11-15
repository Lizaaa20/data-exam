export const money = (v, dec = 0) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  }).format(v ?? 0);

export const num = (v) => new Intl.NumberFormat('en-US').format(v ?? 0);
export const pct = (v) => `${(v ?? 0).toFixed(2)}%`;
export const compacto = (v) =>
  new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(v);
export const fechaHora = (iso) => (iso ? new Date(iso).toLocaleString('es-HN') : '—');

export function inicioUltimoAnio(hasta, minimo) {
  const [y, m, d] = hasta.split('-').map(Number);
  const inicio = new Date(Date.UTC(y - 1, m - 1, d + 1)).toISOString().slice(0, 10);
  return inicio < minimo ? minimo : inicio;
}