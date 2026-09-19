'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, Filter, Search, Send, Users } from 'lucide-react';
import { clsx } from 'clsx';
import type { CampaignMetrics, Physician, SendAlertResponse, TigerDataMetrics } from '@/lib/types';
import { getDoctors } from '@/lib/api';
import { MOCK_CAMPAIGN_METRICS } from '@/lib/mockData';
import { TigerDataBadge } from './TigerDataBadge';
import { NpiSearchBar } from './NpiSearchBar';
import { DoctorTable } from './DoctorTable';
import { SendAlertModal } from './SendAlertModal';
import { AnimatedNumber } from './AnimatedNumber';
import { Spinner } from './Spinner';

interface CampaignConsoleProps {
  onAlertSent: (physician: Physician, response: SendAlertResponse) => void;
  onSelectPhysician?: (physician: Physician) => void;
  onInspectPortal?: (physician: Physician) => void;
  selectedNpi?: string | null;
  metrics?: CampaignMetrics;
}

const filters = [
  { id: 'all', label: 'All records' },
  { id: 'needs-review', label: 'Needs review' },
  { id: 'high-risk', label: 'High signal' },
] as const;
type FilterId = typeof filters[number]['id'];

export function CampaignConsole({ onAlertSent, onSelectPhysician, onInspectPortal, selectedNpi: controlledNpi, metrics: controlledMetrics }: CampaignConsoleProps) {
  const [physicians, setPhysicians] = useState<Physician[]>([]);
  const [tigerMetrics, setTigerMetrics] = useState<TigerDataMetrics | null>(null);
  const [internalMetrics, setInternalMetrics] = useState<CampaignMetrics>(MOCK_CAMPAIGN_METRICS);
  const [internalNpi, setInternalNpi] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<FilterId>('needs-review');
  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const activeNpi = controlledNpi !== undefined ? controlledNpi : internalNpi;
  const activeMetrics = controlledMetrics ?? internalMetrics;
  const selectedPhysician = physicians.find((physician) => physician.npi === activeNpi) ?? null;

  useEffect(() => {
    getDoctors().then((data) => { setPhysicians(data.physicians); setTigerMetrics(data.tiger_data_metrics); }).catch(console.error).finally(() => setLoading(false));
  }, []);

  const filteredPhysicians = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return physicians.filter((physician) => {
      const matchesQuery = !normalized || [physician.npi, physician.nppes.legal_name, physician.nppes.primary_specialty].some((value) => value.toLowerCase().includes(normalized));
      const matchesFilter = filter === 'all' || (filter === 'needs-review' ? physician.unreviewed_count > 0 : physician.mismatch_score >= .7);
      return matchesQuery && matchesFilter;
    });
  }, [filter, physicians, query]);

  const handleSelect = useCallback((physician: Physician) => { setInternalNpi(physician.npi); onSelectPhysician?.(physician); }, [onSelectPhysician]);
  const handleAlertSent = useCallback((response: SendAlertResponse) => { if (!selectedPhysician) return; setInternalMetrics((metrics) => ({ ...metrics, dispatched: metrics.dispatched + 1 })); onAlertSent(selectedPhysician, response); }, [onAlertSent, selectedPhysician]);

  return <div className="rounded-[20px] border border-[var(--c-border)] bg-[var(--c-surface)] p-5 shadow-[0_18px_50px_rgba(0,0,0,.2)] sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-[.14em] text-[#78e3d7]">Outreach queue</p><h1 className="mt-1 text-2xl font-bold tracking-[-.035em] text-[var(--c-text-primary)]">Prioritize a thoughtful review.</h1><p className="mt-1 max-w-xl text-sm leading-5 text-[var(--c-text-secondary)]">Identify records with meaningful review signals, then prepare a secure portal link only when it is useful to the clinician.</p></div>
      {tigerMetrics && <TigerDataBadge metrics={tigerMetrics} />}
    </div>

    <div className="mt-6 rounded-xl border border-[var(--c-border)] bg-[var(--c-bg-secondary)] p-3"><div className="mb-2 flex items-center justify-between"><p className="text-xs font-semibold text-[var(--c-text-primary)]">Look up an NPI</p><span className="text-xs text-[var(--c-text-muted)]">Registry enrichment</span></div><NpiSearchBar onResult={(result) => { const match = physicians.find((physician) => physician.npi === result.npi); if (match) handleSelect(match); }} /></div>

    <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-2"><Users size={16} className="text-[#78e3d7]" /><div><h2 className="text-sm font-semibold text-[var(--c-text-primary)]">Review queue</h2><p className="text-xs text-[var(--c-text-muted)]">{filteredPhysicians.length} of {physicians.length || '—'} HCP records</p></div></div><label className="relative block sm:w-56"><Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--c-text-dim)]" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name, NPI, specialty" className="w-full rounded-lg border border-[var(--c-border)] bg-[#071720] py-2 pl-9 pr-3 text-xs text-[var(--c-text-primary)] placeholder:text-[var(--c-text-dim)]" /></label></div>
    <div className="mt-3 flex items-center gap-1 overflow-x-auto pb-1"><Filter size={14} className="mr-1 shrink-0 text-[var(--c-text-muted)]" />{filters.map((item) => <button key={item.id} onClick={() => setFilter(item.id)} className={clsx('shrink-0 rounded-full px-3 py-1.5 text-xs font-medium transition', filter === item.id ? 'bg-[#3bd0bd] text-[#071720]' : 'bg-[#153542] text-[var(--c-text-secondary)] hover:bg-[#1d4652]')}>{item.label}</button>)}</div>

    <div className="mt-3">{loading ? <div className="grid min-h-72 place-items-center rounded-xl border border-dashed border-[var(--c-border)]"><div className="text-center"><Spinner size={24} className="mx-auto" /><p className="mt-3 text-xs text-[var(--c-text-muted)]">Loading records…</p></div></div> : <DoctorTable physicians={filteredPhysicians} selectedNpi={activeNpi} onSelect={handleSelect} />}</div>

    <div className="mt-5 grid gap-3 xl:grid-cols-[1fr_auto]"><PipelineFunnel metrics={activeMetrics} /><div className="flex flex-col gap-2 sm:flex-row xl:flex-col"><button onClick={() => selectedPhysician && setModalOpen(true)} disabled={!selectedPhysician} className={clsx('inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-semibold transition', selectedPhysician ? 'bg-[#3bd0bd] text-[#071720] hover:bg-[#78e3d7] glow-green' : 'cursor-not-allowed bg-[#17323d] text-[var(--c-text-dim)]')}><Send size={15} />{selectedPhysician ? 'Create review link' : 'Select an HCP'}</button>{selectedPhysician && onInspectPortal && <button onClick={() => onInspectPortal(selectedPhysician)} className="min-h-11 rounded-xl border border-[var(--c-border)] px-4 text-sm font-semibold text-[var(--c-text-secondary)] transition hover:border-[#3bd0bd] hover:text-[#78e3d7]">Open review</button>}</div></div>
    <SendAlertModal open={modalOpen} physician={selectedPhysician} onClose={() => setModalOpen(false)} onSent={handleAlertSent} />
  </div>;
}

function PipelineFunnel({ metrics }: { metrics: CampaignMetrics }) {
  const stages = [{ label: 'Links created', value: metrics.dispatched }, { label: 'Opened', value: metrics.opened }, { label: 'Notices ready', value: metrics.disputed }, { label: 'Protected', value: metrics.claimed }];
  return <div className="rounded-xl border border-[var(--c-border)] bg-[var(--c-bg-secondary)] p-3.5"><div className="mb-3 flex items-center gap-2"><Activity size={15} className="text-[#78e3d7]" /><p className="text-xs font-semibold uppercase tracking-[.12em] text-[var(--c-text-muted)]">Journey overview</p></div><div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{stages.map((stage) => <div key={stage.label} className="rounded-lg bg-[#102d39] px-3 py-2.5"><p className="font-mono text-lg font-bold text-[var(--c-text-primary)]"><AnimatedNumber value={stage.value} format={(value) => Math.round(value).toString()} /></p><p className="mt-0.5 text-[11px] text-[var(--c-text-muted)]">{stage.label}</p></div>)}</div></div>;
}
