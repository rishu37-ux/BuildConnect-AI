import { useState } from 'react';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { formatPhone, PROFESSIONS, STATES, STATUSES } from '../lib/labels.js';

function Row({ label, children }) {
  return (
    <div className="grid grid-cols-3 gap-2 py-2 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="col-span-2 break-words">{children || '—'}</dd>
    </div>
  );
}

export default function LeadDrawer({ lead, users, onClose, onSaved, onDeleted }) {
  const { user, can } = useAuth();
  const editable = can('leads:write') || (can('leads:write:own') && lead.assigned_to === user.id);
  const [form, setForm] = useState({ status: lead.status, notes: lead.notes ?? '', assigned_to: lead.assigned_to ?? '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function save() {
    setSaving(true);
    setError('');
    try {
      const patch = { status: form.status, notes: form.notes };
      if (can('leads:assign')) patch.assigned_to = form.assigned_to === '' ? null : Number(form.assigned_to);
      onSaved(await api.updateLead(lead.id, patch));
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete ${lead.full_name}? This cannot be undone.`)) return;
    try {
      await api.deleteLead(lead.id);
      onDeleted(lead.id);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-slate-900/30" onClick={onClose}>
      <aside className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">{lead.full_name}</h2>
            {lead.firm_name && <p className="text-sm text-slate-500">{lead.firm_name}</p>}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="Close">✕</button>
        </div>

        <dl className="divide-y divide-slate-100">
          <Row label="Profession">{PROFESSIONS[lead.profession]}</Row>
          <Row label="Mobile">
            {lead.phone_e164 && <a className="text-indigo-600" href={`tel:${lead.phone_e164}`}>{formatPhone(lead.phone_e164)}</a>}
          </Row>
          <Row label="Email">{lead.email && <a className="text-indigo-600" href={`mailto:${lead.email}`}>{lead.email}</a>}</Row>
          <Row label="Location">{[...new Set([lead.city, lead.district, STATES[lead.state]])].filter(Boolean).join(', ')}</Row>
          <Row label="Website">{lead.website}</Row>
          <Row label="Source">
            <a className="text-indigo-600" href={lead.source_url} target="_blank" rel="noreferrer noopener">{lead.source_domain}</a>
          </Row>
          <Row label="Confidence">{Math.round(lead.confidence * 100)}%</Row>
          <Row label="Last seen">{new Date(lead.last_seen_at).toLocaleString('en-IN')}</Row>
        </dl>

        <div className="mt-6 space-y-3">
          <label className="block text-sm">
            <span className="font-medium">Status</span>
            <select disabled={!editable} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-2 disabled:bg-slate-50">
              {Object.entries(STATUSES).map(([v, s]) => <option key={v} value={v}>{s.label}</option>)}
            </select>
          </label>
          {can('leads:assign') && (
            <label className="block text-sm">
              <span className="font-medium">Assigned to</span>
              <select value={form.assigned_to} onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-2">
                <option value="">Unassigned</option>
                {users.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}
              </select>
            </label>
          )}
          <label className="block text-sm">
            <span className="font-medium">Notes</span>
            <textarea disabled={!editable} rows={4} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 disabled:bg-slate-50" />
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-between">
            {can('leads:delete') ? (
              <button onClick={remove} className="text-sm text-red-600 hover:text-red-800">Delete lead</button>
            ) : <span />}
            {editable && (
              <button onClick={save} disabled={saving}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
                {saving ? 'Saving…' : 'Save'}
              </button>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}
