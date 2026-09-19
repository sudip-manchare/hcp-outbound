'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, CheckCircle2, ExternalLink, RotateCcw, ShieldCheck, Sparkles } from 'lucide-react';
import { clsx } from 'clsx';
import type { CampaignMetrics, DisputeNotice, Physician, PortalStep, SendAlertResponse } from '@/lib/types';
import { CampaignConsole } from '@/components/CampaignConsole';
import { AuditCard } from '@/components/AuditCard';
import { DisputeNoticeModal } from '@/components/DisputeNoticeModal';
import { EnrollmentConfirmation } from '@/components/EnrollmentConfirmation';
import { generateDispute } from '@/lib/api';
import { MOCK_CAMPAIGN_METRICS, MOCK_PHYSICIANS, buildMockDisputeNotice } from '@/lib/mockData';

export default function Home() {
  const [selectedPhysician, setSelectedPhysician] = useState<Physician | null>(null);
  const [auditToken, setAuditToken] = useState<string | null>(null);
  const [step, setStep] = useState<PortalStep>('audit');
  const [disputeNotice, setDisputeNotice] = useState<DisputeNotice | null>(null);
  const [loadingDispute, setLoadingDispute] = useState(false);
  const [campaignMetrics, setCampaignMetrics] = useState<CampaignMetrics>(MOCK_CAMPAIGN_METRICS);
  const [lastDispatchedNpi, setLastDispatchedNpi] = useState<string | null>(null);

  const selectPhysician = useCallback((physician: Physician) => {
    setSelectedPhysician(physician);
    setAuditToken((current) => current ?? `mock_token_${physician.npi}`);
    setStep('audit');
    setDisputeNotice(null);
  }, []);

  const handleAlertSent = useCallback((physician: Physician, response: SendAlertResponse) => {
    setSelectedPhysician(physician);
    setAuditToken(response.audit_token);
    setLastDispatchedNpi(physician.npi);
    setStep('audit');
    setDisputeNotice(null);
    setCampaignMetrics((metrics) => ({ ...metrics, dispatched: metrics.dispatched + 1 }));
  }, []);

  const handleDispute = useCallback(async () => {
    if (!selectedPhysician) return;
    setLoadingDispute(true);
    try {
      const notice = await generateDispute(selectedPhysician.npi, auditToken ?? `mock_token_${selectedPhysician.npi}`);
      setDisputeNotice(notice);
    } catch {
      setDisputeNotice(buildMockDisputeNotice(selectedPhysician));
    } finally {
      setStep('notice');
      setCampaignMetrics((metrics) => ({ ...metrics, disputed: metrics.disputed + 1 }));
      setLoadingDispute(false);
    }
  }, [auditToken, selectedPhysician]);

  const handleEnroll = useCallback(() => {
    setStep('enrolled');
    setCampaignMetrics((metrics) => ({ ...metrics, claimed: metrics.claimed + 1 }));
  }, []);

  const resetWorkspace = () => {
    setSelectedPhysician(null);
    setAuditToken(null);
    setDisputeNotice(null);
    setLastDispatchedNpi(null);
    setStep('audit');
  };

  const activeToken = auditToken ?? (selectedPhysician ? `mock_token_${selectedPhysician.npi}` : null);

  return (
    <main className="min-h-screen bg-[var(--c-bg)] text-[var(--c-text-primary)]">
      <header className="sticky top-0 z-30 border-b border-[var(--c-border)] bg-[#071720]/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-5 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <BrandMark />
            <div className="hidden h-6 w-px bg-[var(--c-border)] sm:block" />
            <p className="hidden truncate text-sm font-medium text-[var(--c-text-secondary)] sm:block">Open Payments review workspace</p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className="hidden rounded-full border border-[#22625f] bg-[#0d373a] px-3 py-1.5 font-medium text-[#78e3d7] sm:inline-flex">HCP-first outreach</span>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-5 sm:px-6 lg:py-7">
        <section aria-label="Campaign review queue" className="min-w-0"><CampaignConsole onAlertSent={handleAlertSent} onSelectPhysician={selectPhysician} onInspectPortal={selectPhysician} selectedNpi={selectedPhysician?.npi ?? null} metrics={campaignMetrics} /></section>
        <section aria-label="Physician audit workspace" className="min-w-0">
          <div className="overflow-hidden rounded-[20px] border border-[var(--c-border)] bg-[var(--c-surface)] shadow-[0_18px_50px_rgba(0,0,0,.22)]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--c-border)] px-5 py-4 sm:px-6">
              <div><p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--c-text-muted)]">Review workspace</p><p className="mt-1 text-sm font-semibold text-[var(--c-text-primary)]">{selectedPhysician ? `Audit for Dr. ${selectedPhysician.nppes.last_name}` : 'Select an HCP to start a review'}</p></div>
              {selectedPhysician ? <div className="flex items-center gap-2">{activeToken && <Link href={`/audit/${activeToken}`} target="_blank" className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--c-border)] px-2.5 py-2 text-xs font-medium text-[var(--c-text-secondary)] transition hover:border-[#3bd0bd] hover:text-[#78e3d7]"><ExternalLink size={13} />Open portal</Link>}<button onClick={resetWorkspace} className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium text-[var(--c-text-secondary)] transition hover:bg-[var(--c-surface-hover)]"><RotateCcw size={13} />Clear</button></div> : <span className="rounded-full bg-[var(--c-bg-secondary)] px-2.5 py-1 text-xs font-medium text-[var(--c-text-muted)]">No record selected</span>}
            </div>
            {selectedPhysician && <WorkflowSteps step={step} />}
            {selectedPhysician && lastDispatchedNpi === selectedPhysician.npi && <div className="mx-5 mt-4 flex items-start gap-2 rounded-xl border border-[#22625f] bg-[#0d373a] px-3 py-2.5 text-xs text-[#78e3d7] sm:mx-6"><CheckCircle2 size={15} className="mt-px shrink-0" /><span>Secure review link created for this HCP. The portal preview is ready below.</span></div>}
            <div className="min-h-[580px]"><AnimatePresence mode="wait">{!selectedPhysician ? <EmptyWorkspace key="empty" onSelect={selectPhysician} /> : <motion.div key={`${selectedPhysician.npi}-${step}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: .18 }} className="h-full">{step === 'audit' && <AuditCard physician={selectedPhysician} auditToken={activeToken ?? `mock_token_${selectedPhysician.npi}`} onDispute={handleDispute} loadingDispute={loadingDispute} />}{step === 'notice' && disputeNotice && <DisputeNoticeModal notice={disputeNotice} onContinue={handleEnroll} inline />}{step === 'enrolled' && <div className="min-h-[580px]"><EnrollmentConfirmation physician={selectedPhysician} /></div>}</motion.div>}</AnimatePresence></div>
          </div>
        </section>
      </div>
    </main>
  );
}

function BrandMark() { return <div className="flex items-center gap-2.5"><Image src="/falsepay-fp-white.png" width={32} height={32} alt="" className="h-8 w-8 rounded-[10px] bg-[#102d39] p-0.5" priority /><span className="text-base font-bold tracking-[-.03em] text-[#edf7f8]">FalsePay</span></div>; }

function WorkflowSteps({ step }: { step: PortalStep }) {
  const items: { label: string; step: PortalStep }[] = [{ label: 'Review', step: 'audit' }, { label: 'Notice', step: 'notice' }, { label: 'Protection', step: 'enrolled' }];
  const activeIndex = items.findIndex((item) => item.step === step);
  return <div className="flex items-center gap-2 border-b border-[var(--c-border)] bg-[var(--c-bg-secondary)] px-5 py-3 sm:px-6">{items.map((item, index) => <div className="flex items-center gap-2" key={item.step}><div className={clsx('grid h-5 w-5 place-items-center rounded-full text-[10px] font-bold', index < activeIndex ? 'bg-[#3bd0bd] text-[#071720]' : index === activeIndex ? 'bg-[#56b8ca] text-[#071720]' : 'bg-[#183543] text-[var(--c-text-muted)]')}>{index < activeIndex ? <CheckCircle2 size={12} /> : index + 1}</div><span className={clsx('text-xs font-medium', index === activeIndex ? 'text-[var(--c-text-primary)]' : 'text-[var(--c-text-muted)]')}>{item.label}</span>{index < items.length - 1 && <span className="mx-1 h-px w-6 bg-[var(--c-border)]" />}</div>)}</div>;
}

function EmptyWorkspace({ onSelect }: { onSelect: (physician: Physician) => void }) {
  return <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex min-h-[580px] flex-col justify-between p-6 sm:p-8"><div className="max-w-md"><div className="mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-[#103c43] text-[#78e3d7]"><ShieldCheck size={24} /></div><p className="text-xs font-semibold uppercase tracking-[.14em] text-[#78e3d7]">A clearer path to review</p><h1 className="mt-2 text-2xl font-bold tracking-[-.035em] text-[var(--c-text-primary)]">Give HCPs a concise, defensible view of reported payments.</h1><p className="mt-3 text-sm leading-6 text-[var(--c-text-secondary)]">Start with a prioritized record above. This workspace separates clinical review, notice preparation, and optional monitoring steps.</p></div><div><p className="mb-2 text-xs font-semibold uppercase tracking-[.14em] text-[var(--c-text-muted)]">Priority examples</p><div className="space-y-2">{MOCK_PHYSICIANS.slice(0, 3).map((physician) => <button key={physician.npi} onClick={() => onSelect(physician)} className="group flex w-full items-center justify-between rounded-xl border border-[var(--c-border)] px-3.5 py-3 text-left transition hover:border-[#3bd0bd] hover:bg-[#10343d]"><span><span className="block text-sm font-semibold text-[var(--c-text-primary)]">{physician.nppes.legal_name}</span><span className="mt-0.5 block text-xs text-[var(--c-text-muted)]">{physician.nppes.primary_specialty} · {physician.unreviewed_count} items awaiting review</span></span><ArrowRight size={16} className="text-[var(--c-text-dim)] transition group-hover:translate-x-1 group-hover:text-[#78e3d7]" /></button>)}</div><div className="mt-5 flex items-start gap-2 rounded-xl bg-[#0b2c35] p-3 text-xs leading-5 text-[var(--c-text-secondary)]"><Sparkles size={14} className="mt-0.5 shrink-0 text-[#78e3d7]" />Risk signals are surfaced as evidence to review—not as a conclusion about a payment.</div></div></motion.div>;
}
