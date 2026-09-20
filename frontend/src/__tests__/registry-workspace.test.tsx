import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import Home from '@/app/page';
import { enrichNpi } from '@/lib/api';
import type { NppesEnrichment, Physician } from '@/lib/types';

vi.mock('@/lib/api', () => ({ enrichNpi: vi.fn(), generateDispute: vi.fn() }));
vi.mock('@/components/CampaignConsole', () => ({
  CampaignConsole: ({ onSelectPhysician }: { onSelectPhysician: (p: Physician) => void }) =>
    <>{['1111111111', '2222222222'].map((npi) => <button key={npi} onClick={() => onSelectPhysician(physician(npi))}>{npi}</button>)}</>,
}));
vi.mock('@/components/AuditCard', () => ({
  AuditCard: ({ physician: p }: { physician: Physician }) => <div data-testid="profile">{p.nppes.legal_name} {p.total_amount}</div>,
}));

function physician(npi: string): Physician {
  return {
    npi, nppes: { npi, legal_name: 'CMS name', first_name: 'CMS', last_name: 'name', credential: '', taxonomy_code: '', taxonomy_desc: '', primary_specialty: '', address: { address_1: '', city: '', state: '', postal_code: '' }, verified: false, enriched_at: '' },
    payments: [], total_amount: 123, meal_count: 0, unreviewed_count: 0, mismatch_score: 0, risk_level: 'low',
  };
}

afterEach(() => { cleanup(); vi.resetAllMocks(); });

it('loads registry information on selection and ignores a stale response', async () => {
  let resolveFirst!: (value: NppesEnrichment) => void;
  vi.mocked(enrichNpi).mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
    .mockResolvedValueOnce({ ...physician('2222222222').nppes, legal_name: 'Second registry clinician' });
  render(<Home />);
  fireEvent.click(screen.getByRole('button', { name: '1111111111' }));
  expect(screen.getByRole('status')).toHaveTextContent('Loading NPPES');
  fireEvent.click(screen.getByRole('button', { name: '2222222222' }));
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent('Second registry clinician 123'));
  await act(async () => resolveFirst({ ...physician('1111111111').nppes, legal_name: 'Stale clinician' }));
  expect(screen.getByTestId('profile')).toHaveTextContent('Second registry clinician 123');
  expect(enrichNpi).toHaveBeenNthCalledWith(2, '2222222222');
});

it('keeps CMS information when the registry lookup fails', async () => {
  vi.mocked(enrichNpi).mockRejectedValueOnce(new Error('Unavailable'));
  render(<Home />);
  fireEvent.click(screen.getByRole('button', { name: '1111111111' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Showing the retained CMS information');
  await waitFor(() => expect(screen.getByTestId('profile')).toHaveTextContent('CMS name 123'));
});
