'use client';

import { useEffect, useState } from 'react';
import type { DisputeNotice, Physician } from '@/lib/types';
import { AuditCard } from '@/components/AuditCard';
import { DisputeNoticeModal } from '@/components/DisputeNoticeModal';
import { EnrollmentConfirmation } from '@/components/EnrollmentConfirmation';
import { generateDispute, getAuditCardByToken } from '@/lib/api';

interface AuditPageClientProps {
  auditToken: string;
}

type Step = 'audit' | 'notice' | 'enrolled';

export function AuditPageClient({ auditToken }: AuditPageClientProps) {
  const [physician, setPhysician] = useState<Physician | null>(null);
  const [step, setStep] = useState<Step>('audit');
  const [notice, setNotice] = useState<DisputeNotice | null>(null);
  const [loadingDispute, setLoadingDispute] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getAuditCardByToken(auditToken)
      .then((data) => { if (active) setPhysician(data.physician); })
      .catch(() => { if (active) setError('This secure review link is unavailable or has expired.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [auditToken]);

  const handleDispute = async () => {
    if (!physician) return;
    setLoadingDispute(true);
    try {
      const generated = await generateDispute(physician.npi, auditToken);
      setNotice(generated);
      setStep('notice');
    } catch {
      setError('The dispute notice could not be prepared from the API response.');
    } finally {
      setLoadingDispute(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col">
      {loading && <p className="p-6 text-sm text-[var(--c-text-muted)]">Loading secure review…</p>}
      {error && <p role="alert" className="m-5 rounded-lg border border-[#663d42] bg-[#351f28] px-3 py-2 text-xs text-[#f5aaa5]">{error}</p>}
      {!loading && physician && step === 'audit' && (
        <AuditCard
          physician={physician}
          auditToken={auditToken}
          onDispute={handleDispute}
          loadingDispute={loadingDispute}
          mobile
        />
      )}

      {physician && step === 'notice' && notice && (
        <DisputeNoticeModal
          notice={notice}
          onContinue={() => setStep('enrolled')}
          inline
        />
      )}

      {physician && step === 'enrolled' && (
        <EnrollmentConfirmation physician={physician} />
      )}
    </div>
  );
}
