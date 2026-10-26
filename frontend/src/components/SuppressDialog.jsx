import { useState } from 'react';
import { api } from '../lib/api.js';

/** Record a do-not-contact / erasure request (DPDP Act 2023). */
export default function SuppressDialog({ onClose, onDone }) {
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  async function submit(e) {
    e.preventDefault();
    setError('');
    try {
      setResult(await api.suppress(value, reason));
      onDone();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-slate-900/30 px-4" onClick={onClose}>
      <form onSubmit={submit} onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md space-y-4 rounded-xl bg-white p-6 shadow-xl">
        <div>
          <h2 className="text-lg font-semibold">Opt-out / erasure request</h2>
          <p className="text-sm text-slate-500">
            Deletes any matching lead and blocks this contact from future scrapes.
          </p>
        </div>
        <input required placeholder="Mobile number or email" value={value} onChange={(e) => setValue(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
        <input placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
        {error && <p className="text-sm text-red-600">{error}</p>}
        {result && (
          <p className="text-sm text-emerald-700">
            Suppressed {result.kind}; {result.leads_deleted} lead(s) deleted.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-3 py-2 text-sm">Close</button>
          <button className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700">Suppress</button>
        </div>
      </form>
    </div>
  );
}
