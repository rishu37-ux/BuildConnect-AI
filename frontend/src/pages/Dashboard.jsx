import { useCallback, useEffect, useState } from 'react';
import Filters from '../components/Filters.jsx';
import LeadDrawer from '../components/LeadDrawer.jsx';
import LeadTable from '../components/LeadTable.jsx';
import Pagination from '../components/Pagination.jsx';
import StatCards from '../components/StatCards.jsx';
import Campaigns from './Campaigns.jsx';
import SuppressDialog from '../components/SuppressDialog.jsx';
import { api } from '../lib/api.js';
import { useAuth } from '../lib/auth.jsx';

const INITIAL_FILTERS = {
  q: '', state: '', profession: '', status: '', assignedTo: '', hasPhone: false, hasEmail: false,
  sort: 'created_at', order: 'desc', page: 1, pageSize: 25,
};

export default function Dashboard() {
  const { user, logout, can } = useAuth();
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [result, setResult] = useState({ data: [], total: 0 });
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showSuppress, setShowSuppress] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [tab, setTab] = useState('leads');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [leads, s] = await Promise.all([api.leads(filters), api.stats()]);
      setResult(leads);
      setStats(s);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    const t = setTimeout(load, filters.q ? 300 : 0); // debounce typing in search
    return () => clearTimeout(t);
  }, [load, filters.q]);

  useEffect(() => {
    if (can('leads:assign')) api.users().then(setUsers).catch(() => {});
  }, [can]);

  const updateFilters = (patch) => setFilters((f) => ({ ...f, page: 1, ...patch }));

  async function onExport() {
    setExporting(true);
    try {
      await api.exportCsv(filters);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  }

  function onLeadSaved(updated) {
    setResult((r) => ({ ...r, data: r.data.map((l) => (l.id === updated.id ? updated : l)) }));
    setSelected(updated);
  }

  function onLeadDeleted(id) {
    setSelected(null);
    setResult((r) => ({ ...r, total: r.total - 1, data: r.data.filter((l) => l.id !== id) }));
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div>
            <h1 className="text-lg font-semibold">BuildConnect AI</h1>
            <p className="text-xs text-slate-500">Architects · Structural engineers · Contractors — Punjab &amp; Himachal Pradesh</p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-slate-600 sm:inline">{user.full_name}</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium capitalize text-slate-700">{user.role}</span>
            <button onClick={logout} className="text-slate-500 hover:text-slate-900">Sign out</button>
          </div>
        </div>
        {can('runs:read') && (
          <nav className="mx-auto flex max-w-7xl gap-6 px-4 text-sm sm:px-6">
            {[['leads', 'Leads'], ['campaigns', 'Campaigns (AI agents)']].map(([key, label]) => (
              <button key={key} onClick={() => setTab(key)}
                className={`border-b-2 pb-2 font-medium ${tab === key
                  ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
                {label}
              </button>
            ))}
          </nav>
        )}
      </header>

      {tab === 'campaigns' ? <Campaigns onLeadsChanged={load} /> : (
      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        <StatCards stats={stats} />

        <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-4">
            <Filters filters={filters} onChange={updateFilters} users={users} />
            <div className="flex gap-2">
              {can('suppression:manage') && (
                <button onClick={() => setShowSuppress(true)}
                  className="rounded-md border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50">
                  Opt-out request
                </button>
              )}
              {can('leads:export') && (
                <button onClick={onExport} disabled={exporting}
                  className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
                  {exporting ? 'Exporting…' : 'Export CSV'}
                </button>
              )}
            </div>
          </div>

          {error && <p className="border-b border-red-100 bg-red-50 px-4 py-2 text-sm text-red-700">{error}</p>}

          <LeadTable
            leads={result.data}
            loading={loading}
            sort={filters.sort}
            order={filters.order}
            onSort={(sort) => updateFilters({ sort, order: filters.sort === sort && filters.order === 'desc' ? 'asc' : 'desc' })}
            onSelect={setSelected}
            users={users}
          />
          <Pagination page={filters.page} pageSize={filters.pageSize} total={result.total}
            onPage={(page) => setFilters((f) => ({ ...f, page }))} />
        </section>
      </main>
      )}

      {selected && (
        <LeadDrawer lead={selected} users={users} onClose={() => setSelected(null)}
          onSaved={onLeadSaved} onDeleted={onLeadDeleted} />
      )}
      {showSuppress && <SuppressDialog onClose={() => setShowSuppress(false)} onDone={load} />}
    </div>
  );
}
