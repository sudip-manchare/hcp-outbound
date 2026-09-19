import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Badge } from '@/components/Badge';
import { AuditCard } from '@/components/AuditCard';
import { DisputeNoticeModal } from '@/components/DisputeNoticeModal';
import { EnrollmentConfirmation } from '@/components/EnrollmentConfirmation';
import { SendAlertModal } from '@/components/SendAlertModal';
import { MOCK_PHYSICIANS, buildMockDisputeNotice } from '@/lib/mockData';
import * as api from '@/lib/api';

// ─── Badge Tests ──────────────────────────────────────────────────────────────

describe('Badge', () => {
  it('renders the label text', () => {
    render(<Badge variant="verified" label="NPPES Verified" />);
    expect(screen.getByText('NPPES Verified')).toBeInTheDocument();
  });

  it('renders the verified icon', () => {
    render(<Badge variant="verified" label="Verified" />);
    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('renders mismatch badge with warning icon', () => {
    render(<Badge variant="mismatch" label="Mismatch" />);
    expect(screen.getByText('⚠')).toBeInTheDocument();
  });

  it('renders critical badge with red color class', () => {
    const { container } = render(<Badge variant="critical" label="Critical" />);
    expect(container.firstChild).toHaveClass('text-red-300');
  });

  it('renders low badge without icon', () => {
    render(<Badge variant="low" label="Low" />);
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('applies sm size by default', () => {
    const { container } = render(<Badge variant="low" label="Test" />);
    expect(container.firstChild).toHaveClass('text-xs');
  });

  it('applies md size when specified', () => {
    const { container } = render(<Badge variant="low" label="Test" size="md" />);
    expect(container.firstChild).toHaveClass('text-sm');
  });

  it('applies custom className', () => {
    const { container } = render(<Badge variant="low" label="Test" className="custom-class" />);
    expect(container.firstChild).toHaveClass('custom-class');
  });
});

// ─── AuditCard Tests ──────────────────────────────────────────────────────────

describe('AuditCard', () => {
  const physician = MOCK_PHYSICIANS[0]; // Dr. Jane Miller (Dermatology, has unreviewed payments)
  const onDispute = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders physician details and credentials', async () => {
    render(
      <AuditCard
        physician={physician}
        auditToken={`mock_token_${physician.npi}`}
        onDispute={onDispute}
      />,
    );

    expect(await screen.findByText(new RegExp(physician.nppes.last_name, 'i'))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(physician.npi, 'i'))).toBeInTheDocument();
    expect(screen.getByText(physician.nppes.primary_specialty)).toBeInTheDocument();
  });

  it('renders specialty mismatch warning for anomalous physician', async () => {
    render(
      <AuditCard
        physician={physician}
        auditToken={`mock_token_${physician.npi}`}
        onDispute={onDispute}
      />,
    );

    expect(await screen.findByText(/Specialty Mismatch Detected/i)).toBeInTheDocument();
  });

  it('triggers onDispute when Dispute button is clicked', async () => {
    const user = userEvent.setup();
    render(
      <AuditCard
        physician={physician}
        auditToken={`mock_token_${physician.npi}`}
        onDispute={onDispute}
      />,
    );

    const disputeBtn = await screen.findByRole('button', { name: /Dispute Unreviewed Items/i });
    await user.click(disputeBtn);
    expect(onDispute).toHaveBeenCalledTimes(1);
  });
});

// ─── DisputeNoticeModal Tests ──────────────────────────────────────────────────

describe('DisputeNoticeModal', () => {
  const physician = MOCK_PHYSICIANS[0];
  const mockNotice = buildMockDisputeNotice(physician);
  const onContinue = vi.fn();

  it('renders formal statutory citation 42 CFR § 403.908', () => {
    render(<DisputeNoticeModal notice={mockNotice} onContinue={onContinue} inline />);
    expect(screen.getAllByText(/42 CFR § 403.908/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(new RegExp(mockNotice.notice_id, 'i'))).toBeInTheDocument();
  });

  it('renders disputing physician information and disputed total', () => {
    render(<DisputeNoticeModal notice={mockNotice} onContinue={onContinue} inline />);
    expect(screen.getByText(mockNotice.physician_name)).toBeInTheDocument();
    expect(screen.getByText(mockNotice.physician_npi)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(mockNotice.total_disputed_amount.toLocaleString()))).toBeInTheDocument();
  });

  it('calls onContinue when clicking Start ongoing monitoring', async () => {
    const user = userEvent.setup();
    render(<DisputeNoticeModal notice={mockNotice} onContinue={onContinue} inline />);
    const continueBtn = screen.getByRole('button', { name: /Start ongoing monitoring/i });
    await user.click(continueBtn);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});

// ─── EnrollmentConfirmation Tests ─────────────────────────────────────────────

describe('EnrollmentConfirmation', () => {
  const physician = MOCK_PHYSICIANS[0];

  it('renders review-ready confirmation', () => {
    render(<EnrollmentConfirmation physician={physician} />);
    expect(screen.getByText('Notice ready for review')).toBeInTheDocument();
    expect(screen.getByText('Ongoing monitoring active')).toBeInTheDocument();
  });

  it('lists ongoing monitoring benefits without SMS references', () => {
    render(<EnrollmentConfirmation physician={physician} />);
    expect(screen.getByText(/Year-round CMS payment monitoring/i)).toBeInTheDocument();
    expect(screen.getByText(/Real-time Open Payments anomaly alerts/i)).toBeInTheDocument();
    expect(screen.queryByText(/via SMS/i)).not.toBeInTheDocument();
  });
});

// ─── SendAlertModal Tests ──────────────────────────────────────────────────────

describe('SendAlertModal', () => {
  const physician = MOCK_PHYSICIANS[0];
  const onClose = vi.fn();
  const onSent = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders secure-link modal with 1-click tokenized channel', () => {
    render(
      <SendAlertModal
        open={true}
        physician={physician}
        onClose={onClose}
        onSent={onSent}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Create secure review link' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create secure review link/i })).toBeInTheDocument();
    expect(screen.getByText(/1-Click Zero-Login Token/i)).toBeInTheDocument();
    expect(screen.getAllByText(new RegExp(`mock_token_${physician.npi}`)).length).toBeGreaterThanOrEqual(1);
    // Does NOT render phone number input
    expect(screen.queryByPlaceholderText(/\+1/)).not.toBeInTheDocument();
  });

  it('dispatches alert when clicking button', async () => {
    const user = userEvent.setup();
    vi.spyOn(api, 'sendAlert').mockResolvedValueOnce({
      success: true,
      audit_token: `mock_token_${physician.npi}`,
      audit_url: `http://localhost:3000/audit/mock_token_${physician.npi}`,
      message: 'Alert dispatched',
      simulated: true,
    });

    render(
      <SendAlertModal
        open={true}
        physician={physician}
        onClose={onClose}
        onSent={onSent}
      />,
    );

    const dispatchBtn = screen.getByRole('button', { name: /Create secure review link/i });
    await user.click(dispatchBtn);

    await waitFor(() => {
      expect(onSent).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });
});
