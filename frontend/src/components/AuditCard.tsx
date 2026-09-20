'use client';

import { useMemo, useState } from 'react';
import { Building2, CheckCircle2, Clock3, DollarSign, ShieldCheck, Utensils } from 'lucide-react';
import { clsx } from 'clsx';
import type { Physician, RiskTriageAssessment } from '@/lib/types';
import { createRiskTriage } from '@/lib/api';
import { RiskExplanationCard } from './RiskExplanationCard';

interface AuditCardProps { physician: Physician; auditToken: string; onDispute: () => void; loadingDispute?: boolean; mobile?: boolean; riskAssessment?: RiskTriageAssessment; }

export function AuditCard({ physician, mobile = false, riskAssessment }: AuditCardProps) {
  const [generatedAssessment, setGeneratedAssessment] = useState<RiskTriageAssessment | null>(null);
  const [triageError, setTriageError] = useState<string | null>(null);
  const [triagingPaymentId, setTriagingPaymentId] = useState<string | null>(null);

  const unreviewed = physician.payments.filter((payment) => !payment.reviewed);
  const modelOutliers = physician.payments.filter((payment) => (payment.risk_score ?? 0) > 0);
  // Mock/demo records predate model scores; live stored data always uses the
  // model-outlier set so a selected queue row opens only relevant payments.
  const reviewPayments = modelOutliers.length ? modelOutliers : unreviewed;
  const topManufacturers = useMemo(() => Object.values(physician.payments.reduce<Record<string, { name: string; total_amount: number }>>((groups, payment) => {
    const group = groups[payment.manufacturer] ?? { name: payment.manufacturer, total_amount: 0 };
    group.total_amount += payment.amount;
    groups[payment.manufacturer] = group;
    return groups;
  }, {})).sort((left, right) => right.total_amount - left.total_amount).slice(0, 2), [physician.payments]);
  const activeAssessment = riskAssessment ?? generatedAssessment;
  const explainPayment = async (payment: Physician['payments'][number]) => {
    setTriagingPaymentId(payment.id);
    setGeneratedAssessment(null);
    setTriageError(null);
    try {
      // In the live contract, payment.id is the immutable CMS record ID.
      setGeneratedAssessment(await createRiskTriage(payment.id, payment.payment_date));
    } catch {
      setTriageError('We could not prepare an evidence-backed explanation for this record. Please try again.');
    } finally {
      setTriagingPaymentId(null);
    }
  };

  return <div className={clsx('bg-[var(--c-surface)]', mobile ? 'min-h-[calc(100dvh-96px)]' : '')}>
    <div className="border-b border-[var(--c-border)] bg-[linear-gradient(110deg,#0b3655,#0f6075)] px-5 py-5 text-white sm:px-6"><div className="flex items-center gap-2 text-xs text-[#c6f6ef]"><ShieldCheck size={15} /><span className="font-semibold">Secure clinician review</span><span className="ml-auto rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-[10px] font-medium">{physician.nppes.enriched_at ? (physician.nppes.verified ? 'NPPES matched · Active' : 'NPPES record retrieved') : 'CMS reported'}</span></div><h2 className="mt-4 text-xl font-bold tracking-[-.03em]">Dr. {physician.nppes.first_name} {physician.nppes.last_name}, {physician.nppes.credential}</h2><div className="mt-1 flex items-center gap-2 text-sm text-[#d6eaf0]"><span>{physician.nppes.primary_specialty}</span><span className="text-white/40">·</span><span>NPI {physician.npi}</span></div></div>
    <div className="space-y-5 p-5 sm:p-6">
      {physician.nppes.enriched_at && <RegistryDetails physician={physician} />}
      <div className="grid grid-cols-3 gap-2.5"><Stat icon={<DollarSign size={15} />} label="Reported total" value={`$${physician.total_amount.toLocaleString()}`} /><Stat icon={<Utensils size={15} />} label="Meals" value={String(physician.meal_count)} /><Stat icon={<Clock3 size={15} />} label="To review" value={String(physician.unreviewed_count)} emphasize={physician.unreviewed_count > 0} /></div>
      <div className="rounded-xl border border-[#22625f] bg-[#0d373a] p-3.5"><div className="flex items-start gap-2.5"><CheckCircle2 size={16} className="mt-0.5 shrink-0 text-[#78e3d7]" /><div><p className="text-sm font-semibold text-[#d7faf5]">Your review starts with the record.</p><p className="mt-0.5 text-xs leading-5 text-[var(--c-text-secondary)]">Compare each entry with your own records. A payment is not a finding; it is information that may need clarification.</p></div></div></div>
      {activeAssessment && <RiskExplanationCard assessment={activeAssessment} />}
      {triageError && <p role="alert" className="rounded-xl border border-[#663d42] bg-[#351f28] px-3 py-2 text-xs text-[#f5aaa5]">{triageError}</p>}
      {reviewPayments.length > 0 ? <div><div className="mb-2.5 flex items-end justify-between"><div><p className="text-xs font-semibold uppercase tracking-[.12em] text-[var(--c-text-muted)]">Model outliers to review</p><p className="mt-1 text-sm font-semibold text-[var(--c-text-primary)]">{reviewPayments.length} flagged item{reviewPayments.length > 1 ? 's' : ''}</p></div><span className="text-xs text-[var(--c-text-muted)]">{physician.nppes.address.city}, {physician.nppes.address.state}</span></div><div className="space-y-2">{reviewPayments.map((payment) => <div key={payment.id} className="flex items-center justify-between gap-3 rounded-xl border border-[var(--c-border)] bg-[#0b202b] p-3"><div className="min-w-0"><p className="truncate text-sm font-semibold text-[var(--c-text-primary)]">{payment.manufacturer}</p><p className="mt-0.5 text-xs text-[var(--c-text-muted)]">{payment.nature_of_payment} · {payment.payment_date}</p></div><div className="text-right"><p className="font-mono text-sm font-semibold text-[var(--c-text-primary)]">${payment.amount.toLocaleString()}</p><div className="mt-1.5 flex justify-end gap-3"><button onClick={() => void explainPayment(payment)} disabled={triagingPaymentId !== null} className="text-[11px] font-semibold text-[#78e3d7] hover:text-[#b5fff4] disabled:text-[var(--c-text-muted)]">{triagingPaymentId === payment.id ? 'Preparing explanation…' : 'Explain this record'}</button></div></div></div>)}</div></div> : <div className="rounded-xl border border-[var(--c-border)] bg-[var(--c-bg-secondary)] p-5 text-center"><CheckCircle2 size={22} className="mx-auto text-[#78e3d7]" /><p className="mt-2 text-sm font-semibold text-[var(--c-text-primary)]">No model outliers currently await review.</p></div>}
      {topManufacturers.length > 0 && <div className="rounded-xl bg-[var(--c-bg-secondary)] p-3.5"><div className="flex items-center gap-2"><Building2 size={14} className="text-[var(--c-text-muted)]" /><p className="text-xs font-semibold uppercase tracking-[.12em] text-[var(--c-text-muted)]">Reporting organizations</p></div><div className="mt-3 grid grid-cols-2 gap-2">{topManufacturers.map((manufacturer) => <div key={manufacturer.name} className="rounded-lg bg-[#102d39] px-3 py-2"><p className="truncate text-xs font-medium text-[var(--c-text-primary)]">{manufacturer.name}</p><p className="mt-1 font-mono text-xs text-[var(--c-text-secondary)]">${manufacturer.total_amount.toLocaleString()}</p></div>)}</div></div>}
    </div>
  </div>;
}

function Stat({ icon, label, value, emphasize = false }: { icon: React.ReactNode; label: string; value: string; emphasize?: boolean }) { return <div className={clsx('rounded-xl border p-3', emphasize ? 'border-[#775c28] bg-[#302714]' : 'border-[var(--c-border)] bg-[#0b202b]')}><div className={clsx('mb-2', emphasize ? 'text-[#f4c46e]' : 'text-[#78e3d7]')}>{icon}</div><p className={clsx('truncate font-mono text-base font-bold', emphasize ? 'text-[#f4c46e]' : 'text-[var(--c-text-primary)]')}>{value}</p><p className="mt-0.5 text-[11px] text-[var(--c-text-muted)]">{label}</p></div>; }

function RegistryDetails({ physician }: { physician: Physician }) {
  const provider = physician.nppes;
  const details = [
    ['Credentials', provider.credential],
    ['Practice address', [provider.address.address_1, provider.address.city, provider.address.state, provider.address.postal_code].filter(Boolean).join(', ')],
    ['Practice phone', provider.telephone_number],
    ['Primary specialty', provider.primary_specialty],
    ['Registered specialties', provider.specialties?.join('; ')],
    ['Reported license', [provider.license_number, provider.license_state].filter(Boolean).join(' · ')],
    ['NPI status', provider.registry_status === 'A' ? 'Active' : provider.registry_status],
    ['Registered since', provider.enumeration_date],
    ['Registry last updated', provider.last_updated],
  ];
  return <section aria-label="NPPES registry details" className="rounded-xl border border-[var(--c-border)] bg-[var(--c-bg-secondary)] p-4">
    <h3 className="text-sm font-semibold text-[var(--c-text-primary)]">NPPES registry details</h3>
    <dl className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {details.map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-xs text-[var(--c-text-muted)]">{label}</dt><dd className="mt-1 break-words text-sm text-[var(--c-text-primary)]">{value || 'Not reported'}</dd></div>)}
    </dl>
  </section>;
}
