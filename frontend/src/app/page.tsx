'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, ExternalLink, RotateCcw, ShieldCheck } from 'lucide-react';
import { clsx } from 'clsx';
import type { DisputeNotice, Physician, PortalStep } from '@/lib/types';
import { CampaignConsole } from '@/components/CampaignConsole';
import { AuditCard } from '@/components/AuditCard';
import { DisputeNoticeModal } from '@/components/DisputeNoticeModal';
import { EnrollmentConfirmation } from '@/components/EnrollmentConfirmation';
import { enrichNpi, generateDispute } from '@/lib/api';

export default function Home() {
  const workspaceRef = useRef<HTMLElement>(null);
  const [selectedPhysician, setSelectedPhysician] = useState<Physician | null>(null);
  const [auditToken, setAuditToken] = useState<string | null>(null);
  const [step, setStep] = useState<PortalStep>('audit');
  const [disputeNotice, setDisputeNotice] = useState<DisputeNotice | null>(null);
  const [loadingDispute, setLoadingDispute] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [registryLoading, setRegistryLoading] = useState(false);
  const selectedNpi = selectedPhysician?.npi;

  useEffect(() => {
    if (!selectedNpi) return;
    let cancelled = false;
    void enrichNpi(selectedNpi).then((enrichment) => {
      if (cancelled) return;
      setSelectedPhysician((current) => current?.npi === selectedNpi
        ? { ...current, nppes: enrichment }
        : current);
    }).catch(() => {
      if (!cancelled) setRegistryError('Registry details are unavailable. Showing the retained CMS information.');
    }).finally(() => {
      if (!cancelled) setRegistryLoading(false);
    });
    return () => { cancelled = true; };
  }, [selectedNpi]);

  const selectPhysician = useCallback((physician: Physician) => {
    workspaceRef.current?.scrollIntoView?.({
      behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
      block: 'start',
    });
    if (physician.npi === selectedNpi) return;
    setRegistryLoading(true);
    setRegistryError(null);
    setSelectedPhysician(physician);
    setAuditToken(null);
    setStep('audit');
    setDisputeNotice(null);
    setWorkflowError(null);
  }, [selectedNpi]);

  const handleDispute = useCallback(async () => {
    if (!selectedPhysician || !auditToken) return;
    setLoadingDispute(true);
    try {
      const notice = await generateDispute(selectedPhysician.npi, auditToken);
      setDisputeNotice(notice);
      setStep('notice');
    } catch {
      setWorkflowError('The dispute notice could not be prepared from the API response.');
    } finally {
      setLoadingDispute(false);
    }
  }, [auditToken, selectedPhysician]);

  const handleEnroll = useCallback(() => {
    setStep('enrolled');
  }, []);

  const resetWorkspace = () => {
    setRegistryLoading(false);
    setRegistryError(null);
    setSelectedPhysician(null);
    setAuditToken(null);
    setDisputeNotice(null);
    setStep('audit');
  };

  const activeToken = auditToken;

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
        <section aria-label="Campaign review queue" className="min-w-0"><CampaignConsole onSelectPhysician={selectPhysician} selectedNpi={selectedPhysician?.npi ?? null} /></section>
        <section ref={workspaceRef} aria-label="Physician audit workspace" className="min-w-0 scroll-mt-20">
          <div className="overflow-hidden rounded-[20px] border border-[var(--c-border)] bg-[var(--c-surface)] shadow-[0_18px_50px_rgba(0,0,0,.22)]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--c-border)] px-5 py-4 sm:px-6">
              <div><p className="text-xs font-semibold uppercase tracking-[.14em] text-[var(--c-text-muted)]">Review workspace</p><p className="mt-1 text-sm font-semibold text-[var(--c-text-primary)]">{selectedPhysician ? `Audit for Dr. ${selectedPhysician.nppes.last_name}` : 'Select an HCP to start a review'}</p></div>
              {selectedPhysician ? <div className="flex items-center gap-2">{activeToken && <Link href={`/audit/${activeToken}`} target="_blank" className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--c-border)] px-2.5 py-2 text-xs font-medium text-[var(--c-text-secondary)] transition hover:border-[#3bd0bd] hover:text-[#78e3d7]"><ExternalLink size={13} />Open portal</Link>}<button onClick={resetWorkspace} className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium text-[var(--c-text-secondary)] transition hover:bg-[var(--c-surface-hover)]"><RotateCcw size={13} />Clear</button></div> : <span className="rounded-full bg-[var(--c-bg-secondary)] px-2.5 py-1 text-xs font-medium text-[var(--c-text-muted)]">No record selected</span>}
            </div>
            {selectedPhysician && <WorkflowSteps step={step} />}
            {selectedPhysician && registryLoading && <p role="status" className="px-5 py-3 text-center text-sm text-[var(--c-text-secondary)]">Loading NPPES registry details…</p>}
            {selectedPhysician && registryError && <p role="alert" className="px-5 py-3 text-center text-sm text-[#f4c46e]">{registryError}</p>}
            {workflowError && <p role="alert" className="mx-5 mt-4 rounded-lg border border-[#663d42] bg-[#351f28] px-3 py-2 text-xs text-[#f5aaa5] sm:mx-6">{workflowError}</p>}
            <div className="flex flex-col items-center"><AnimatePresence mode="wait">{!selectedPhysician ? <EmptyWorkspace key="empty" /> : <motion.div key={`${selectedPhysician.npi}-${step}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: .18 }} className="w-full min-w-0">{step === 'audit' && <AuditCard physician={selectedPhysician} auditToken={activeToken ?? ''} onDispute={handleDispute} loadingDispute={loadingDispute} />}{step === 'notice' && disputeNotice && <DisputeNoticeModal notice={disputeNotice} onContinue={handleEnroll} inline />}{step === 'enrolled' && <EnrollmentConfirmation physician={selectedPhysician} />}</motion.div>}</AnimatePresence></div>
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

function EmptyWorkspace() {
  return <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex w-full items-center justify-center px-6 py-8 sm:px-8 sm:py-10"><div className="flex max-w-md flex-col items-center text-center"><div className="mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-[#103c43] text-[#78e3d7]"><ShieldCheck size={24} /></div><p className="text-xs font-semibold uppercase tracking-[.14em] text-[#78e3d7]">API-backed review</p><h1 className="mt-2 text-2xl font-bold tracking-[-.035em] text-[var(--c-text-primary)]">Select a clinician from the current CMS review queue.</h1><p className="mt-3 text-sm leading-6 text-[var(--c-text-secondary)]">This workspace displays only records returned by the backend. Pull the latest CMS data if the queue is empty.</p></div></motion.div>;
}
