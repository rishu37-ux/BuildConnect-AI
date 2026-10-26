import { formatPhone, PROFESSIONS, STATES, STATUSES } from '../lib/labels.js';

function SortHeader({ field, label, sort, order, onSort }) {
  const active = sort === field;
  return (
    <th className="px-4 py-3 text-left">
      <button onClick={() => onSort(field)} className="inline-flex items-center gap-1 font-medium hover:text-slate-900">
        {label}
        <span className="text-[10px]">{active ? (order === 'asc' ? '▲' : '▼') : ''}</span>
      </button>
    </th>
  );
}

export default function LeadTable({ leads, loading, sort, order, onSort, onSelect, users }) {
  const userName = Object.fromEntries(users.map((u) => [u.id, u.full_name]));
  const sortProps = { sort, order, onSort };

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <SortHeader field="full_name" label="Name" {...sortProps} />
            <th className="px-4 py-3 text-left font-medium">Profession</th>
            <th className="px-4 py-3 text-left font-medium">Mobile</th>
            <th className="px-4 py-3 text-left font-medium">Email</th>
            <SortHeader field="city" label="Location" {...sortProps} />
            <th className="px-4 py-3 text-left font-medium">Status</th>
            {users.length > 0 && <th className="px-4 py-3 text-left font-medium">Assigned</th>}
            <SortHeader field="confidence" label="Conf." {...sortProps} />
            <SortHeader field="created_at" label="Added" {...sortProps} />
          </tr>
        </thead>
        <tbody className={`divide-y divide-slate-100 ${loading ? 'opacity-50' : ''}`}>
          {leads.length === 0 && (
            <tr>
              <td colSpan={9} className="px-4 py-12 text-center text-slate-500">
                {loading ? 'Loading…' : 'No leads match these filters.'}
              </td>
            </tr>
          )}
          {leads.map((lead) => (
            <tr key={lead.id} onClick={() => onSelect(lead)} className="cursor-pointer hover:bg-indigo-50/50">
              <td className="px-4 py-3">
                <div className="font-medium">{lead.full_name}</div>
                {lead.firm_name && lead.firm_name !== lead.full_name && (
                  <div className="text-xs text-slate-500">{lead.firm_name}</div>
                )}
              </td>
              <td className="px-4 py-3 text-slate-600">{PROFESSIONS[lead.profession]}</td>
              <td className="whitespace-nowrap px-4 py-3 tabular-nums">{formatPhone(lead.phone_e164)}</td>
              <td className="px-4 py-3 text-slate-600">{lead.email}</td>
              <td className="px-4 py-3 text-slate-600">
                {[lead.city, STATES[lead.state]].filter(Boolean).join(', ')}
              </td>
              <td className="px-4 py-3">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUSES[lead.status].className}`}>
                  {STATUSES[lead.status].label}
                </span>
              </td>
              {users.length > 0 && <td className="px-4 py-3 text-slate-600">{userName[lead.assigned_to] ?? '—'}</td>}
              <td className="px-4 py-3 tabular-nums text-slate-600">{Math.round(lead.confidence * 100)}%</td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-500">{new Date(lead.created_at).toLocaleDateString('en-IN')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
