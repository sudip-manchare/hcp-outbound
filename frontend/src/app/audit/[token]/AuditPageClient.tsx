'use client';

import { useState } from 'react';
import type { Physician, DisputeNotice } from '@/lib/types';
import { AuditCard } from '@/components/AuditCard';
import { DisputeNoticeModal } from '@/components/DisputeNoticeModal';
import { EnrollmentConfirmation } from '@/components/EnrollmentConfirmation';
import { generateDispute } from '@/lib/api';

interface AuditPageClientProps {
  physician: Physician;
  auditToken: string;
}

type Step = 'audit' | 'notice' | 'enrolled';

export function AuditPageClient({ physician, auditToken }: AuditPageClientProps) {
  const [step, setStep] = useState<Step>('audit');
  const [notice, setNotice] = useState<DisputeNotice | null>(null);
  const [loadingDispute, setLoadingDispute] = useState(false);

  const handleDispute = async () => {
    setLoadingDispute(true);
    try {
      const generated = await generateDispute(physician.npi, auditToken);
      setNotice(generated);
      setStep('notice');
    } catch {
      setStep('notice');
    } finally {
      setLoadingDispute(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col">
      {step === 'audit' && (
        <AuditCard
          physician={physician}
          auditToken={auditToken}
          onDispute={handleDispute}
          loadingDispute={loadingDispute}
          mobile
        />
      )}

      {step === 'notice' && notice && (
        <DisputeNoticeModal
          notice={notice}
          onContinue={() => setStep('enrolled')}
          inline
        />
      )}

      {step === 'enrolled' && (
        <EnrollmentConfirmation physician={physician} />
      )}
    </div>
  );
}

