'use client';

import { FileText, CheckCircle, ChevronRight, Calendar, User, Building } from 'lucide-react';
import type { DisputeNotice } from '@/lib/types';

interface DisputeNoticeModalProps {
  notice: DisputeNotice;
  onContinue: () => void;
  inline?: boolean;
}

export function DisputeNoticeModal({ notice, onContinue, inline = false }: DisputeNoticeModalProps) {
  const formattedDate = new Date(notice.generated_at).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  const content = (
    <div className="flex flex-col h-full overflow-auto">
      {/* Success header */}
      <div className="bg-gradient-to-r from-[#0b3655] to-[#0d9388] px-4 pt-4 pb-5 flex-shrink-0">
        <div className="flex items-center gap-2 mb-2">
          <CheckCircle size={16} className="text-[#d7faf5]" />
          <span className="text-xs text-[#d7faf5] font-medium">Notice prepared for review</span>
        </div>
        <h3 className="text-white font-bold text-sm leading-tight">
          42 CFR § 403.908 Formal Dispute Notice
        </h3>
        <p className="text-[#d7faf5] text-xs mt-1">
          Notice ID: <span className="font-mono">{notice.notice_id}</span>
        </p>
      </div>

      {/* Notice body - styled like a formal legal document */}
      <div className="flex-1 overflow-auto bg-slate-50 px-4 py-4 space-y-3">
        {/* Document header */}
        <div className="text-center border-b border-slate-200 pb-3">
          <div className="flex items-center justify-center gap-1.5 mb-1">
            <FileText size={14} className="text-slate-600" />
            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              CMS Open Payments Dispute Notice
            </span>
          </div>
          <p className="text-xs text-slate-500 font-mono">Pursuant to {notice.legal_citation}</p>
          <p className="text-xs text-slate-500">Date: {formattedDate}</p>
        </div>

        {/* Physician info */}
        <Section icon={<User size={12} />} title="Disputing Physician">
          <Field label="Name" value={notice.physician_name} />
          <Field label="NPI" value={notice.physician_npi} mono />
          <Field label="Specialty" value={`${notice.physician_specialty}, ${notice.physician_credential}`} />
          <Field label="Address" value={notice.physician_address} />
        </Section>

        {/* Manufacturer info */}
        <Section icon={<Building size={12} />} title="Respondent Manufacturer">
          <Field label="Name" value={notice.manufacturer_name} />
          <Field label="Compliance Contact" value={notice.manufacturer_contact} />
        </Section>

        {/* Disputed payments */}
        <Section icon={<Calendar size={12} />} title={`Disputed Payments (${notice.disputed_payments.length})`}>
          {notice.disputed_payments.map((p) => (
            <div key={p.id} className="flex justify-between text-xs py-1 border-b border-slate-100 last:border-0">
              <div>
                <p className="text-slate-700 font-medium">{p.nature_of_payment}</p>
                <p className="text-slate-400">{p.payment_date}</p>
              </div>
              <span className="text-slate-800 font-bold font-mono">${p.amount.toLocaleString()}</span>
            </div>
          ))}
          <div className="flex justify-between pt-2 text-xs font-bold">
            <span className="text-slate-600">Total Disputed</span>
            <span className="text-slate-900 font-mono">${notice.total_disputed_amount.toLocaleString()}</span>
          </div>
        </Section>

        {/* Legal notice text */}
        <div className="bg-slate-100 rounded-lg p-3">
          <p className="text-xs text-slate-600 leading-relaxed">
            This notice is submitted pursuant to {notice.legal_citation} requesting correction of the above-listed payment records. The reporting entity has 45 days to correct or contest this dispute through the CMS Open Payments system.
          </p>
        </div>
      </div>

      {/* CTA */}
      <div className="bg-slate-50 px-4 py-4 flex-shrink-0 border-t border-slate-200">
        <button
          onClick={onContinue}
          className="w-full py-3 rounded-xl bg-[#0b3655] hover:bg-[#124768] text-white font-bold text-sm flex items-center justify-center gap-2 transition-colors"
        >
          Start ongoing monitoring
          <ChevronRight size={16} />
        </button>
        <p className="text-center text-xs text-slate-400 mt-2">
          Keep a secure record and receive future review signals
        </p>
      </div>
    </div>
  );

  if (inline) return <div className="h-full">{content}</div>;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="glass-strong rounded-2xl w-[440px] max-h-[90vh] overflow-hidden">
        {content}
      </div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-slate-500">{icon}</span>
        <p className="text-xs font-bold text-slate-600 uppercase tracking-wider">{title}</p>
      </div>
      <div className="pl-2 space-y-1">{children}</div>
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-2 text-xs">
      <span className="text-slate-400 w-20 flex-shrink-0">{label}:</span>
      <span className={`text-slate-700 ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}
