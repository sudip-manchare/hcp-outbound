'use client';

import { useState } from 'react';
import { Send, ShieldAlert, Link as LinkIcon, MapPin, CheckCircle2 } from 'lucide-react';
import { clsx } from 'clsx';
import { Modal } from './Modal';
import { Spinner } from './Spinner';
import { Badge } from './Badge';
import type { Physician, SendAlertResponse } from '@/lib/types';
import { sendAlert } from '@/lib/api';

interface SendAlertModalProps {
  open: boolean;
  physician: Physician | null;
  onClose: () => void;
  onSent: (response: SendAlertResponse) => void;
}

export function SendAlertModal({ open, physician, onClose, onSent }: SendAlertModalProps) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const handleSend = async () => {
    if (!physician) return;
    setSending(true);
    setError('');
    try {
      const res = await sendAlert({
        npi: physician.npi,
        channel: 'portal_link',
      });
      onSent(res);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send');
    } finally {
      setSending(false);
    }
  };

  if (!physician) return null;

  return (
    <Modal open={open} onClose={onClose} title="Create secure review link" className="w-[500px]">
      <div className="space-y-4">
        {/* Physician summary */}
        <div className="rounded-xl border border-[var(--c-border)] bg-[#f9fbfc] p-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-[var(--c-text-primary)] text-base">{physician.nppes.legal_name}</p>
            {physician.nppes.verified && <Badge variant="verified" label="NPPES Verified" />}
          </div>
          <p className="text-xs text-[var(--c-text-secondary)]">
            {physician.nppes.primary_specialty} · NPI <span className="font-mono text-[var(--c-text-primary)]">{physician.npi}</span>
          </p>
          <div className="flex items-center gap-1.5 text-xs text-[var(--c-text-muted)]">
            <MapPin size={12} />
            <span>{physician.nppes.address.city}, {physician.nppes.address.state}</span>
          </div>
          <div className="flex gap-4 pt-2 border-t border-[var(--c-border)] mt-2">
            <Stat label="Reported Total" value={`$${physician.total_amount.toLocaleString()}`} />
            <Stat label="Unreviewed" value={String(physician.unreviewed_count)} highlight={physician.unreviewed_count > 0} />
          </div>
        </div>

        {/* Secure Dispatch Channel */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-[var(--c-text-secondary)]">
            <span className="font-medium flex items-center gap-1.5">
              <LinkIcon size={12} className="text-[#0d9388]" />
              Review access
            </span>
            <span className="text-[#08796f] flex items-center gap-1">
              <CheckCircle2 size={11} /> 1-Click Zero-Login Token
            </span>
          </div>
          <div className="w-full bg-[#f7fafb] border border-[var(--c-border)] rounded-lg px-3 py-2 text-xs text-[var(--c-text-secondary)]">
            A secure API-generated link will appear after dispatch.
          </div>
        </div>

        {/* Outbound alert preview */}
        <div className="bg-[#f3fbfa] rounded-xl p-3.5 border border-[#bde7e1] space-y-1.5">
          <div className="flex items-center gap-1.5">
            <ShieldAlert size={13} className="text-[#bd7c1d]" />
            <p className="text-xs text-[#477481] font-semibold uppercase tracking-wider">Review message preview</p>
          </div>
          <p className="text-xs text-[var(--c-text-secondary)] leading-relaxed">
            <strong>FalsePay secure review:</strong> Dr. {physician.nppes.last_name}, {physician.unreviewed_count} reported items totaling <strong>${physician.total_amount.toLocaleString()}</strong> are available for review under NPI {physician.npi}. The API-generated secure link is included only after a successful dispatch.
          </p>
        </div>

        {error && <p className="text-xs text-red-400" role="alert">{error}</p>}

        <button
          onClick={handleSend}
          disabled={sending}
          className={clsx(
            'w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition-all',
            sending
              ? 'bg-slate-700 text-slate-500 cursor-not-allowed'
              : 'bg-[#0b3655] hover:bg-[#124768] text-white glow-blue',
          )}
        >
          {sending ? (
            <><Spinner size={16} className="text-blue-300" /> Dispatching Alert...</>
          ) : (
            <><Send size={15} /> Create secure review link</>
          )}
        </button>
      </div>
    </Modal>
  );
}

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <p className="text-xs text-[var(--c-text-muted)]">{label}</p>
      <p className={clsx('text-sm font-bold font-mono', highlight ? 'text-[#bd7c1d]' : 'text-[var(--c-text-primary)]')}>{value}</p>
    </div>
  );
}
