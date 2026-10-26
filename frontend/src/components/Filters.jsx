import { PROFESSIONS, STATES, STATUSES } from '../lib/labels.js';

const select = 'rounded-md border border-slate-300 bg-white px-2 py-2 text-sm';

export default function Filters({ filters, onChange, users }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <input type="search" placeholder="Search name, firm, city, phone, email…" value={filters.q}
        onChange={(e) => onChange({ q: e.target.value })}
        className="w-64 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none" />
      <select className={select} value={filters.state} onChange={(e) => onChange({ state: e.target.value })}>
        <option value="">All states</option>
        {Object.entries(STATES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <select className={select} value={filters.profession} onChange={(e) => onChange({ profession: e.target.value })}>
        <option value="">All professions</option>
        {Object.entries(PROFESSIONS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <select className={select} value={filters.status} onChange={(e) => onChange({ status: e.target.value })}>
        <option value="">All statuses</option>
        {Object.entries(STATUSES).map(([v, s]) => <option key={v} value={v}>{s.label}</option>)}
      </select>
      {users.length > 0 && (
        <select className={select} value={filters.assignedTo} onChange={(e) => onChange({ assignedTo: e.target.value })}>
          <option value="">Anyone</option>
          <option value="unassigned">Unassigned</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
        </select>
      )}
      <label className="flex items-center gap-1 text-sm text-slate-600">
        <input type="checkbox" checked={filters.hasPhone} onChange={(e) => onChange({ hasPhone: e.target.checked })} />
        Has mobile
      </label>
      <label className="flex items-center gap-1 text-sm text-slate-600">
        <input type="checkbox" checked={filters.hasEmail} onChange={(e) => onChange({ hasEmail: e.target.checked })} />
        Has email
      </label>
    </div>
  );
}
