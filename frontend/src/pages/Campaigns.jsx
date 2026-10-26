import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';
import { PROFESSIONS, STATES } from '../lib/labels.js';

const CAMPAIGN_STATUS = {
  queued: { label: 'Waiting for worker', className: 'bg-slate-100 text-slate-700' },
  running: { label: 'Running', className: 'bg-indigo-100 text-indigo-800' },
  completed: { label: 'Completed', className: 'bg-emerald-100 text-emerald-800' },
  failed: { label: 'Failed', className: 'bg-red-100 text-red-800' },
  cancelled: { label: 'Cancelled', className: 'bg-amber-100 text-amber-800' },
};

const SOURCE_STATUS = {
  queued: 'text-slate-500', crawling: 'text-indigo-600', done: 'text-emerald-700',
  no_leads: 'text-slate-500', blocked: 'text-amber-700', failed: 'text-red-600', skipped: 'text-slate-400',
};

const PHASES = { starting: 'Starting', discovering: 'Discovery agent searching the web', crawling: 'Crawler agents extracting contacts', done: 'Done', cancelled: 'Cancelled' };

const EMPTY_FORM = {
  name: '', professions: ['architect', 'structural_engineer', 'contractor'], states: ['punjab', 'himachal_pradesh'],
  cities: '', max_sites: 30, max_pages_per_site: 25,
};

function toggle(list, value) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function NewCampaign({ onCreated }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const cities = form.cities.split(',').map((c) => c.trim()).filter(Boolean);
      const name = form.name.trim() || `${form.professions.map((p) => PROFESSIONS[p]).join(', ')} — ${
        cities.length ? cities.join(', ') : form.states.map((s) => STATES[s]).join(' & ')}`;
      await api.createCampaign({
        ...form, name: name.slice(0, 200), cities,
        max_sites: Number(form.max_sites), max_pages_per_site: Number(form.max_pages_per_site),
      });
      setForm(EMPTY_FORM);
      onCreated();
    } catch (err) {
      setError(err.details?.fieldErrors ? Object.values(err.details.fieldErrors).flat().join('; ') : err.message);
    } finally {
      setBusy(false);
    }
  }

  const chip = (active) => `rounded-full border px-3 py-1 text-sm ${active
    ? 'border-indigo-600 bg-indigo-50 text-indigo-700' : 'border-slate-300 text-slate-600 hover:bg-slate-50'}`;

  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <h2 className="font-semibold">New campaign</h2>
        <p className="text-sm text-slate-500">
          The discovery agent searches the web for matching firms, then a team of crawler agents visits each
          website in parallel and adds the contacts to your leads.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <p className="mb-2 text-sm font-medium">Who are you looking for?</p>
          <div className="flex flex-wrap gap-2">
            {['architect', 'structural_engineer', 'contractor'].map((p) => (
              <button type="button" key={p} className={chip(form.professions.includes(p))}
                onClick={() => setForm({ ...form, professions: toggle(form.professions, p) })}>
                {PROFESSIONS[p]}
              </button>
            ))}
          </div>
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">Where?</p>
          <div className="flex flex-wrap gap-2">
            {['punjab', 'himachal_pradesh', 'chandigarh'].map((s) => (
              <button type="button" key={s} className={chip(form.states.includes(s))}
                onClick={() => setForm({ ...form, states: toggle(form.states, s) })}>
                {STATES[s]}
              </button>
            ))}
          </div>
        </div>
        <label className="block text-sm">
          <span className="font-medium">Cities</span> <span className="text-slate-500">(optional, comma-separated)</span>
          <input value={form.cities} onChange={(e) => setForm({ ...form, cities: e.target.value })}
            placeholder="e.g. Ludhiana, Mohali, Shimla — blank = all major cities"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" />
        </label>
        <label className="block text-sm">
          <span className="font-medium">Campaign name</span> <span className="text-slate-500">(optional)</span>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" />
        </label>
        <label className="block text-sm">
          <span className="font-medium">Websites to visit</span>
          <input type="number" min={1} max={500} value={form.max_sites}
            onChange={(e) => setForm({ ...form, max_sites: e.target.value })}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" />
        </label>
        <label className="block text-sm">
          <span className="font-medium">Pages per website</span>
          <input type="number" min={1} max={500} value={form.max_pages_per_site}
            onChange={(e) => setForm({ ...form, max_pages_per_site: e.target.value })}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" />
        </label>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex justify-end">
        <button disabled={busy || !form.professions.length || !form.states.length}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {busy ? 'Starting…' : 'Start agents'}
        </button>
      </div>
    </form>
  );
}

function Stat({ label, value }) {
  return (
    <div>
      <p className="text-lg font-semibold tabular-nums">{value ?? 0}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}

function CampaignCard({ campaign, canManage, onChanged }) {
  const [open, setOpen] = useState(false);
  const [sources, setSources] = useState(null);
  const p = campaign.progress ?? {};
  const status = CAMPAIGN_STATUS[campaign.status];
  const active = campaign.status === 'running' || campaign.status === 'queued';
  const total = p.sites_queued || 0;
  const pct = total ? Math.round(((p.sites_crawled ?? 0) / total) * 100) : 0;

  const loadSources = useCallback(() => api.campaignSources(campaign.id).then(setSources).catch(() => {}), [campaign.id]);
  useEffect(() => {
    if (open) loadSources();
  }, [open, loadSources, campaign.progress]);

  async function cancel() {
    if (!window.confirm('Stop this campaign? Leads already found are kept.')) return;
    await api.cancelCampaign(campaign.id).catch(() => {});
    onChanged();
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate font-medium">{campaign.name}</h3>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${status.className}`}>{status.label}</span>
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            {campaign.professions.map((x) => PROFESSIONS[x]).join(', ')} ·{' '}
            {campaign.cities.length ? campaign.cities.join(', ') : campaign.states.map((s) => STATES[s]).join(', ')} ·{' '}
            by {campaign.created_by_name ?? '—'} · {new Date(campaign.created_at).toLocaleString('en-IN')}
          </p>
          {campaign.status === 'running' && p.phase && (
            <p className="mt-1 text-xs text-indigo-700">
              {PHASES[p.phase] ?? p.phase}{p.active_agents ? ` · ${p.active_agents} agents working` : ''}
            </p>
          )}
          {campaign.error && <p className="mt-1 text-sm text-red-600">{campaign.error}</p>}
        </div>
        <div className="flex gap-2">
          <button onClick={() => setOpen(!open)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
            {open ? 'Hide websites' : 'Websites'}
          </button>
          {canManage && active && (
            <button onClick={cancel} className="rounded-md border border-red-200 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50">
              Stop
            </button>
          )}
        </div>
      </div>

      {campaign.status === 'running' && total > 0 && (
        <div className="mx-4 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div className="h-full bg-indigo-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 p-4 sm:grid-cols-6">
        <Stat label="Searches" value={p.queries_run} />
        <Stat label="Websites found" value={p.sites_found} />
        <Stat label="Websites visited" value={`${p.sites_crawled ?? 0}/${total}`} />
        <Stat label="Pages read" value={p.pages_fetched} />
        <Stat label="Contacts found" value={p.leads_found} />
        <Stat label="New leads" value={p.leads_new ?? (active ? '…' : 0)} />
      </div>

      {open && (
        <div className="overflow-x-auto border-t border-slate-200">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Website</th>
                <th className="px-4 py-2 text-left font-medium">Found via</th>
                <th className="px-4 py-2 text-left font-medium">Status</th>
                <th className="px-4 py-2 text-right font-medium">Pages</th>
                <th className="px-4 py-2 text-right font-medium">Contacts</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sources === null && <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-500">Loading…</td></tr>}
              {sources?.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-500">No websites yet.</td></tr>
              )}
              {sources?.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-2">
                    <a href={s.url} target="_blank" rel="noreferrer noopener" className="text-indigo-600">{s.domain}</a>
                    {s.title && <div className="max-w-xs truncate text-xs text-slate-500">{s.title}</div>}
                  </td>
                  <td className="px-4 py-2 text-slate-500">{s.discovered_query}</td>
                  <td className={`px-4 py-2 ${SOURCE_STATUS[s.status]}`}>
                    {s.status.replace('_', ' ')}{s.detail ? ` — ${s.detail}` : ''}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{s.pages_crawled}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{s.leads_found}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Campaigns({ onLeadsChanged }) {
  const { can } = useAuth();
  const [campaigns, setCampaigns] = useState([]);
  const [error, setError] = useState('');
  const prevLeads = useRef(0);

  const load = useCallback(async () => {
    try {
      const list = await api.campaigns();
      setCampaigns(list);
      setError('');
      const leads = list.reduce((n, c) => n + (c.progress?.leads_found ?? 0), 0);
      if (leads !== prevLeads.current) {
        prevLeads.current = leads;
        onLeadsChanged?.();
      }
    } catch (err) {
      setError(err.message);
    }
  }, [onLeadsChanged]);

  const anyActive = campaigns.some((c) => c.status === 'running' || c.status === 'queued');
  useEffect(() => {
    load();
    const t = setInterval(load, anyActive ? 4000 : 20000);
    return () => clearInterval(t);
  }, [load, anyActive]);

  const waiting = campaigns.find((c) => c.status === 'queued' && Date.now() - new Date(c.created_at) > 30_000);

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      {can('campaigns:manage') && <NewCampaign onCreated={load} />}
      {waiting && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          “{waiting.name}” is still waiting. Make sure the agent worker is running
          (<code>docker compose up -d worker</code>) and that a search API key is set in <code>.env</code>.
        </p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <section className="space-y-4">
        {campaigns.length === 0 && (
          <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-500">
            No campaigns yet. Start one above and the agents will find leads for you.
          </p>
        )}
        {campaigns.map((c) => (
          <CampaignCard key={c.id} campaign={c} canManage={can('campaigns:manage')} onChanged={load} />
        ))}
      </section>
    </main>
  );
}
