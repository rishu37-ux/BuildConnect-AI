import { PROFESSIONS, STATES } from '../lib/labels.js';

function Card({ label, value, sub }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value ?? '—'}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

const breakdown = (map, labels) =>
  Object.entries(map ?? {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, n]) => `${labels[k] ?? k} ${n}`)
    .join(' · ');

export default function StatCards({ stats }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Card label="Total leads" value={stats?.total} sub={breakdown(stats?.by_state, STATES)} />
      <Card label="Added last 7 days" value={stats?.last_7_days} sub={`${stats?.by_status?.new ?? 0} still new`} />
      <Card label="With mobile" value={stats?.with_phone} sub={`${stats?.with_email ?? 0} with email`} />
      <Card label="In pipeline" value={stats && (stats.by_status?.contacted ?? 0) + (stats.by_status?.qualified ?? 0)}
        sub={breakdown(stats?.by_profession, PROFESSIONS)} />
    </div>
  );
}
