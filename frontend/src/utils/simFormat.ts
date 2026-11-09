/** Formatting helpers for simulated-appliance live data. */

export function formatWatts(w: number | null | undefined): string {
  if (w == null || !Number.isFinite(w)) return '--';
  if (w >= 1000) return `${(w / 1000).toFixed(w >= 10000 ? 0 : 2)} kW`;
  return `${w >= 100 ? Math.round(w) : w.toFixed(w >= 10 ? 0 : 1)} W`;
}

/** "10:30 pm" for an ISO instant (adds the weekday when it isn't today). */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const time = d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' }).replace(':00', '');
  return d.toDateString() === new Date().toDateString() ? time : `${d.toLocaleDateString('en-IN', { weekday: 'short' })} ${time}`;
}

export function formatKWh(v: number): string {
  return v >= 10 ? v.toFixed(1) : v >= 1 ? v.toFixed(2) : v.toFixed(3);
}
