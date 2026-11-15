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