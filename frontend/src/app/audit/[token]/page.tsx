import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import Image from 'next/image';
import { MOCK_PHYSICIANS, buildMockAuditCard } from '@/lib/mockData';
import { AuditPageClient } from './AuditPageClient';

interface AuditPageProps {
  params: Promise<{ token: string }>;
}

export async function generateMetadata({ params }: AuditPageProps): Promise<Metadata> {
  const { token } = await params;
  const npi = token.replace('mock_token_', '');
  const physician = MOCK_PHYSICIANS.find((p) => p.npi === npi);
  return {
    title: physician
      ? `Audit — ${physician.nppes.legal_name} | FalsePay`
      : 'Secure Audit Portal | FalsePay',
    description: 'Review your CMS Open Payments entries and dispute any unauthorized charges.',
    robots: 'noindex,nofollow',
  };
}

/**
 * Standalone zero-login audit portal page.
 * When a physician opens their secure 1-click audit link,
 * this route renders the complete interactive Audit & Dispute flow.
 */
export default async function AuditPage({ params }: AuditPageProps) {
  const { token } = await params;
  const npi = token.replace('mock_token_', '');
  const physician = MOCK_PHYSICIANS.find((p) => p.npi === npi);

  if (!physician) notFound();

  const auditData = buildMockAuditCard(physician);

  return (
    <main
      style={{ background: 'var(--c-bg)', minHeight: '100dvh' }}
      className="flex min-h-[100dvh] flex-col max-w-xl mx-auto border-x border-[var(--c-border)] bg-[var(--c-surface)]"
    >
      {/* Mobile top bar */}
      <header className="sticky top-0 z-10 border-b border-[var(--c-border)] bg-[#071720]/95 px-4 h-14 flex items-center gap-2 backdrop-blur">
        <Image src="/falsepay-fp-white.png" width={28} height={28} alt="" className="h-7 w-7 rounded-lg bg-[#102d39] p-0.5" priority />
        <span className="text-sm font-bold tracking-[-.03em] text-[var(--c-text-primary)]">FalsePay</span>
        <span className="ml-auto text-[11px] text-[var(--c-text-muted)] font-mono truncate">Secure review</span>
      </header>

      {/* Interactive mobile audit & dispute flow */}
      <AuditPageClient
        physician={physician}
        auditToken={auditData.audit_token}
      />

      {/* Footer */}
      <footer className="border-t border-[var(--c-border)] bg-[var(--c-bg-secondary)] px-4 py-3 text-center">
        <p className="text-xs text-[var(--c-text-muted)]">
          Secure review workspace · CMS Open Payments records
        </p>
      </footer>
    </main>
  );
}
