import { AlertTriangle, CheckCircle2, ClipboardList } from 'lucide-react';
import { clsx } from 'clsx';
import type { RiskTriageAssessment } from '@/lib/types';

interface RiskExplanationCardProps {
  assessment: RiskTriageAssessment;
}

const levelLabel = {
  low: 'No priority signals',
  review: 'Review recommended',
  high_priority_review: 'High-priority review',
} as const;

/** Renders only the evidence-grounded explanation supplied by risk triage. */
export function RiskExplanationCard({ assessment }: RiskExplanationCardProps) {
  const needsReview = assessment.review_recommended;
  const ai = assessment.ai_explanation;
  const analysis = ai?.status === 'generated' ? ai.analysis : undefined;
  return (
    <section aria-label="Why this record needs review" className={clsx(
      'rounded-xl border p-3.5',
      needsReview ? 'border-[#705c33] bg-[#302714]' : 'border-[#22625f] bg-[#0d373a]',
    )}>
      <div className="flex items-start gap-2.5">
        {needsReview
          ? <AlertTriangle size={17} className="mt-0.5 shrink-0 text-[#f4c46e]" />
          : <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-[#78e3d7]" />}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-[var(--c-text-primary)]">Record explanation</h3>
            <span className={clsx('rounded-full px-2 py-0.5 text-[10px] font-semibold', needsReview ? 'bg-[#58451f] text-[#f4c46e]' : 'bg-[#153f41] text-[#78e3d7]')}>
              {levelLabel[assessment.risk_level]} · {assessment.risk_score}/100
            </span>
          </div>
          {assessment.payment && <p className="mt-1 text-xs text-[var(--c-text-muted)]">CMS record {assessment.payment.raw_cms_record_id}</p>}
          <p className="mt-3 text-xs font-semibold text-[var(--c-text-primary)]">Isolation Forest result</p>
          <p className="mt-1.5 text-xs leading-5 text-[var(--c-text-secondary)]">{assessment.plain_language_explanation}</p>
        </div>
      </div>
      {assessment.signals.length > 0 && (
        <div className="mt-3 space-y-2 border-t border-white/10 pt-3">
          {assessment.signals.map((signal) => (
            <div key={signal.code} className="flex gap-2 text-xs leading-5 text-[var(--c-text-secondary)]">
              <ClipboardList size={14} className="mt-0.5 shrink-0 text-[var(--c-text-muted)]" />
              <p><span className="font-semibold text-[var(--c-text-primary)]">{signal.title}:</span> {signal.plain_explanation}</p>
            </div>
          ))}
        </div>
      )}
      {analysis && <div className="mt-4 space-y-3 border-t border-white/10 pt-3">
        <h4 className="text-sm font-semibold text-[var(--c-text-primary)]">Gemini qualitative analysis</h4>
        <p className="text-xs leading-5 text-[var(--c-text-secondary)]">{analysis.summary}</p>
        <p className="text-xs leading-5 text-[var(--c-text-secondary)]"><strong>Model interpretation:</strong> {analysis.isolation_forest_interpretation}</p>
        {([
          ['Payment context', analysis.qualitative_context],
          ['Possible benign explanations', analysis.possible_benign_explanations],
          ['Suggested checks', analysis.suggested_checks],
          ['Limitations', analysis.limitations],
        ] as const).map(([title, items]) => <div key={title}>
          <h5 className="text-xs font-semibold text-[var(--c-text-primary)]">{title}</h5>
          <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-[var(--c-text-secondary)]">{items.map((item, index) => <li key={index}>{item}</li>)}</ul>
        </div>)}
        <p className="text-[11px] text-[var(--c-text-muted)]">AI-generated interpretation · {ai?.model} · Based on the supplied record, without web research.</p>
      </div>}
      {ai && ai.status !== 'generated' && <p role="status" className="mt-3 text-xs leading-5 text-[var(--c-text-secondary)]">{ai.message}</p>}
      <p className="mt-3 text-[11px] leading-4 text-[var(--c-text-muted)]">Based on CMS-reported data and comparison records. This is not a determination of fraud or wrongdoing.</p>
    </section>
  );
}
