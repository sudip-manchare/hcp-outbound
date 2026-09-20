'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Filter, RefreshCw, Search, Users } from 'lucide-react';
import { clsx } from 'clsx';
import type { Physician } from '@/lib/types';
import { getDoctors, pullLatestCmsData } from '@/lib/api';
import { DoctorTable } from './DoctorTable';
import { Spinner } from './Spinner';

interface CampaignConsoleProps {
  onSelectPhysician?: (physician: Physician) => void;
  selectedNpi?: string | null;
}

const filters = [
  { id: 'all', label: 'All records' },
  { id: 'needs-review', label: 'Needs review' },
] as const;
type FilterId = typeof filters[number]['id'];
const PAGE_SIZE = 10;

export function CampaignConsole({ onSelectPhysician, selectedNpi: controlledNpi }: CampaignConsoleProps) {
  const [physicians, setPhysicians] = useState<Physician[]>([]);
  const [internalNpi, setInternalNpi] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<FilterId>('all');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const [ingestionMessage, setIngestionMessage] = useState<string | null>(null);
  const [ingestionError, setIngestionError] = useState<string | null>(null);

  const activeNpi = controlledNpi !== undefined ? controlledNpi : internalNpi;

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getDoctors();
      setPhysicians(data.physicians);
    } catch {
      setLoadError('Could not load the review queue. Check the API connection and try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadRecords(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadRecords]);

  const filteredPhysicians = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return physicians.filter((physician) => {
      const matchesQuery = !normalized || [physician.npi, physician.nppes.legal_name, physician.nppes.primary_specialty].some((value) => value.toLowerCase().includes(normalized));
      const outlierScore = physician.risk_score ?? 0;
      const matchesFilter = filter === 'all' || outlierScore > 0;
      return matchesQuery && matchesFilter;
    });
  }, [filter, physicians, query]);
  const totalPages = Math.max(1, Math.ceil(filteredPhysicians.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * PAGE_SIZE;
  const visiblePhysicians = filteredPhysicians.slice(pageStart, pageStart + PAGE_SIZE);
  const firstVisible = filteredPhysicians.length ? pageStart + 1 : 0;
  const lastVisible = Math.min(pageStart + PAGE_SIZE, filteredPhysicians.length);
  const selectFilter = (nextFilter: FilterId) => {
    setFilter(nextFilter);
    setPage(1);
  };
  const updateQuery = (nextQuery: string) => {
    setQuery(nextQuery);
    setPage(1);
  };

  const handleSelect = useCallback((physician: Physician) => { setInternalNpi(physician.npi); onSelectPhysician?.(physician); }, [onSelectPhysician]);
  const handlePullLatest = async () => {
    setIngesting(true);
    setIngestionError(null);
    setIngestionMessage(null);
    try {
      const result = await pullLatestCmsData();
      await loadRecords();
      const invalidated = result.risk_assessments_invalidated;
      setIngestionMessage(`${result.records_inserted} new CMS records loaded. Isolation Forest reviewed ${result.risk_assessments_created} retained payments and flagged ${result.risk_assessments_flagged} for review.${invalidated ? ` ${invalidated} prior assessment${invalidated === 1 ? '' : 's'} retained as history.` : ''}`);
    } catch {
      setIngestionError('Could not pull the latest CMS data. Your current review queue has not changed.');
    } finally {
      setIngesting(false);
    }
  };

  return <div className="rounded-[20px] border border-[var(--c-border)] bg-[var(--c-surface)] p-5 shadow-[0_18px_50px_rgba(0,0,0,.2)] sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-[.14em] text-[#78e3d7]">Outreach queue</p><h1 className="mt-1 text-2xl font-bold tracking-[-.035em] text-[var(--c-text-primary)]">Prioritize a thoughtful review.</h1><p className="mt-1 max-w-xl text-sm leading-5 text-[var(--c-text-secondary)]">The Needs review tab contains clinicians with payments flagged as outliers by the current Isolation Forest run.</p></div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button onClick={() => void handlePullLatest()} disabled={ingesting} className={clsx('inline-flex min-h-9 items-center gap-2 rounded-lg border px-3 text-xs font-semibold transition', ingesting ? 'cursor-not-allowed border-[var(--c-border)] bg-[#17323d] text-[var(--c-text-muted)]' : 'border-[#22625f] bg-[#0d373a] text-[#78e3d7] hover:bg-[#12464a]')}>
          <RefreshCw size={14} className={ingesting ? 'animate-spin' : ''} />
          {ingesting ? 'Pulling CMS data…' : 'Pull most recent data'}
        </button>
      </div>
    </div>
    {ingestionMessage && <p role="status" className="mt-4 rounded-lg border border-[#22625f] bg-[#0d373a] px-3 py-2 text-xs text-[#78e3d7]">{ingestionMessage}</p>}
    {ingestionError && <p role="alert" className="mt-4 rounded-lg border border-[#663d42] bg-[#351f28] px-3 py-2 text-xs text-[#f5aaa5]">{ingestionError}</p>}
    {loadError && <div role="alert" className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-[#663d42] bg-[#351f28] px-3 py-2 text-xs text-[#f5aaa5]"><span>{loadError}</span><button onClick={() => void loadRecords()} className="shrink-0 rounded border border-[#9f5b5e] px-2 py-1 font-semibold hover:bg-[#4a2830]">Retry</button></div>}


    <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-2"><Users size={16} className="text-[#78e3d7]" /><div><h2 className="text-sm font-semibold text-[var(--c-text-primary)]">Review queue</h2><p className="text-xs text-[var(--c-text-muted)]">{filteredPhysicians.length} of {physicians.length || '—'} HCP records</p></div></div><label className="relative block sm:w-56"><Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--c-text-dim)]" /><input value={query} onChange={(event) => updateQuery(event.target.value)} placeholder="Search name, NPI, specialty" className="w-full rounded-lg border border-[var(--c-border)] bg-[#071720] py-2 pl-9 pr-3 text-xs text-[var(--c-text-primary)] placeholder:text-[var(--c-text-dim)]" /></label></div>
    <div className="mt-3 flex items-center gap-1 overflow-x-auto pb-1"><Filter size={14} className="mr-1 shrink-0 text-[var(--c-text-muted)]" />{filters.map((item) => <button key={item.id} onClick={() => selectFilter(item.id)} aria-pressed={filter === item.id} className={clsx('shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition', filter === item.id ? 'bg-[#3bd0bd] text-[#071720]' : 'bg-[#153542] text-[var(--c-text-secondary)] hover:bg-[#1d4652]')}>{item.label}</button>)}</div>

    <div className="mt-3">{loading ? <div className="grid min-h-72 place-items-center rounded-xl border border-dashed border-[var(--c-border)]"><div className="text-center"><Spinner size={24} className="mx-auto" /><p className="mt-3 text-xs text-[var(--c-text-muted)]">Loading records…</p></div></div> : <><DoctorTable physicians={visiblePhysicians} selectedNpi={activeNpi} onSelect={handleSelect} />{filteredPhysicians.length > 0 && <nav aria-label="Review queue pagination" className="mt-3 flex items-center justify-between gap-3 text-xs"><p className="text-[var(--c-text-muted)]">Showing {firstVisible}–{lastVisible} of {filteredPhysicians.length}</p><div className="flex items-center gap-2"><button onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={currentPage === 1} className="rounded-lg border border-[var(--c-border)] px-3 py-1.5 font-medium text-[var(--c-text-secondary)] disabled:cursor-not-allowed disabled:opacity-50">Previous</button><span className="text-[var(--c-text-muted)]">Page {currentPage} of {totalPages}</span><button onClick={() => setPage((current) => Math.min(totalPages, current + 1))} disabled={currentPage === totalPages} className="rounded-lg border border-[var(--c-border)] px-3 py-1.5 font-medium text-[var(--c-text-secondary)] disabled:cursor-not-allowed disabled:opacity-50">Next</button></div></nav>}</>}</div>

  </div>;
}
