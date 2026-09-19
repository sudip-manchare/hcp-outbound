'use client';

import { useMemo, useState } from 'react';
import { ArrowUpDown, CheckCircle2, ChevronDown, ChevronUp, TriangleAlert } from 'lucide-react';
import { clsx } from 'clsx';
import type { Physician } from '@/lib/types';
import { Badge } from './Badge';

type SortKey = 'name' | 'total_amount' | 'mismatch_score' | 'unreviewed_count';
interface DoctorTableProps { physicians: Physician[]; selectedNpi: string | null; onSelect: (physician: Physician) => void; }

export function DoctorTable({ physicians, selectedNpi, onSelect }: DoctorTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('mismatch_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const sorted = useMemo(() => [...physicians].sort((a, b) => {
    const left = sortKey === 'name' ? a.nppes.last_name : a[sortKey];
    const right = sortKey === 'name' ? b.nppes.last_name : b[sortKey];
    return typeof left === 'string' && typeof right === 'string' ? (sortDir === 'asc' ? left.localeCompare(right) : right.localeCompare(left)) : (sortDir === 'asc' ? Number(left) - Number(right) : Number(right) - Number(left));
  }), [physicians, sortDir, sortKey]);
  const toggle = (key: SortKey) => { if (key === sortKey) setSortDir((direction) => direction === 'asc' ? 'desc' : 'asc'); else { setSortKey(key); setSortDir('desc'); } };

  if (!sorted.length) return <div className="grid min-h-56 place-items-center rounded-xl border border-dashed border-[var(--c-border)] px-6 text-center"><div><p className="text-sm font-medium text-[var(--c-text-primary)]">No records match this view.</p><p className="mt-1 text-xs text-[var(--c-text-muted)]">Try changing the signal filter or search terms.</p></div></div>;

  return <div className="overflow-x-auto rounded-xl border border-[var(--c-border)]"><table className="w-full min-w-[660px] border-collapse text-left"><thead><tr className="border-b border-[var(--c-border)] bg-[#0b202b]"><SortHeader label="HCP" col="name" onSort={toggle} active={sortKey === 'name'} direction={sortDir} /><th className="px-4 py-3 text-xs font-semibold text-[var(--c-text-muted)]">Specialty</th><SortHeader label="Reported" col="total_amount" onSort={toggle} active={sortKey === 'total_amount'} direction={sortDir} /><SortHeader label="To review" col="unreviewed_count" onSort={toggle} active={sortKey === 'unreviewed_count'} direction={sortDir} /><SortHeader label="Review signal" col="mismatch_score" onSort={toggle} active={sortKey === 'mismatch_score'} direction={sortDir} /></tr></thead><tbody>{sorted.map((physician) => {
    const selected = physician.npi === selectedNpi;
    const hasSignal = physician.mismatch_score >= .7;
    return <tr key={physician.npi} onClick={() => onSelect(physician)} className={clsx('cursor-pointer border-b border-[var(--c-border)] align-middle transition last:border-b-0', selected ? 'bg-[#103c43]' : 'hover:bg-[#0e2a36]')} aria-selected={selected}><td className="px-4 py-3"><div className="flex items-start gap-2"><span className={clsx('mt-1 h-2 w-2 shrink-0 rounded-full', physician.nppes.verified ? 'bg-[#3bd0bd]' : 'bg-[#64818b]')} title={physician.nppes.verified ? 'NPPES verified' : 'Not yet enriched'} /><div><p className="text-sm font-semibold text-[var(--c-text-primary)]">{physician.nppes.first_name} {physician.nppes.last_name}, {physician.nppes.credential}</p><p className="mt-0.5 font-mono text-[11px] text-[var(--c-text-muted)]">NPI {physician.npi}</p></div></div></td><td className="px-4 py-3 text-xs text-[var(--c-text-secondary)]">{physician.nppes.primary_specialty}</td><td className="px-4 py-3 font-mono text-xs font-semibold text-[var(--c-text-primary)]">${physician.total_amount.toLocaleString()}</td><td className="px-4 py-3"><span className={clsx('inline-flex min-w-6 justify-center rounded-full px-2 py-1 text-xs font-semibold', physician.unreviewed_count ? 'bg-[#3c3017] text-[#f4c46e]' : 'bg-[#153542] text-[var(--c-text-muted)]')}>{physician.unreviewed_count || '—'}</span></td><td className="px-4 py-3">{hasSignal ? <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#f5aaa5]"><TriangleAlert size={14} />{Math.round(physician.mismatch_score * 100)}% mismatch</span> : <span className="inline-flex items-center gap-1.5 text-xs text-[var(--c-text-secondary)]"><CheckCircle2 size={14} className="text-[#78e3d7]" />No high signal</span>}</td></tr>;
  })}</tbody></table></div>;
}

function SortHeader({ label, col, onSort, active, direction }: { label: string; col: SortKey; onSort: (key: SortKey) => void; active: boolean; direction: 'asc' | 'desc'; }) {
  return <th scope="col" className="px-4 py-3"><button onClick={() => onSort(col)} className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--c-text-muted)] transition hover:text-[var(--c-text-primary)]">{label}{active ? direction === 'desc' ? <ChevronDown size={13} /> : <ChevronUp size={13} /> : <ArrowUpDown size={12} className="opacity-50" />}</button></th>;
}
