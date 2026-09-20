import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  createRiskTriage,
  deleteStoredPayment,
  enrichNpi,
  getCmsPayments,
  getCurrentRiskTriage,
  getDoctors,
  getHealth,
  getStoredPayment,
  getStoredPayments,
  pullLatestCmsData,
} from '@/lib/api';

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
    text: vi.fn().mockResolvedValue(JSON.stringify(body)),
  } as unknown as Response;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe('frontend API contract integration', () => {
  it('requests service health and the full filtered CMS preview contract', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: 'ok', sources: { nppes: 'https://nppes.test', cms_open_payments: 'https://cms.test', cms_dataset_id: 'dataset' } }))
      .mockResolvedValueOnce(jsonResponse({ source: {}, filters: {}, pagination: { limit: 5, offset: 2, total_matching_records: 0, returned_records: 0, next_offset: null }, payments: [] }));

    expect((await getHealth()).status).toBe('ok');
    await getCmsPayments({ limit: 5, offset: 2, recipientState: 'OH', manufacturerId: 'm 1', paymentNature: 'Food', recipientType: 'Physician' });

    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8000/health');
    expect(fetchMock.mock.calls[1][0]).toBe('http://localhost:8000/api/payments?limit=5&offset=2&recipient_state=OH&manufacturer_id=m+1&payment_nature=Food&recipient_type=Physician');
  });

  it('uses the local queue and normalizes the actual NPPES provider response for the UI', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ physicians: [], total: 0, tiger_data_metrics: {} }))
      .mockResolvedValueOnce(jsonResponse({
        source: { retrieved_at: '2026-09-19T12:00:00Z' }, npi: '1234567890', status: 'A',
        legal_name: { first_name: 'Ada', last_name: 'Lovelace', credential: 'MD', organization_name: null },
        primary_taxonomy: { code: '207Q00000X', description: 'Family Medicine', license: '123', license_state: 'MA' },
        practice_location: { address_1: '1 Main St', address_2: 'Suite 2', city: 'Boston', state: 'MA', postal_code: '02110', telephone_number: '6175550100' },
        enumeration_date: '2010-01-01', last_updated: '2026-02-17',
        taxonomies: [{ description: 'Family Medicine' }, { description: 'Sports Medicine' }],
      }));

    expect((await getDoctors()).total).toBe(0);
    const enrichment = await enrichNpi('1234567890');

    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8000/api/doctors');
    expect(fetchMock.mock.calls[1][0]).toBe('http://localhost:8000/api/doctors/enrich/1234567890');
    expect(enrichment).toMatchObject({ npi: '1234567890', legal_name: 'Ada Lovelace MD', primary_specialty: 'Family Medicine', verified: true });
    expect(enrichment).toMatchObject({
      telephone_number: '6175550100', license_number: '123', license_state: 'MA',
      registry_status: 'A', enumeration_date: '2010-01-01', last_updated: '2026-02-17',
      specialties: ['Family Medicine', 'Sports Medicine'], address: { address_1: '1 Main St, Suite 2' },
    });
  });

  it('covers CMS ingestion and every stored-payment read, triage, and delete operation', async () => {
    const payment = { raw_cms_record_id: 'cms/record 1', payment_date: '2025-07-24', is_reviewed: false, mismatch_score: null };
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ run_id: 1, records_seen: 1, records_inserted: 1, records_skipped: 0, risk_assessments_invalidated: 0, pagination: { next_offset: null } }, 201))
      .mockResolvedValueOnce(jsonResponse({ records: [payment], pagination: { limit: 10, offset: 0, total_records: 1, returned_records: 1, next_offset: null } }))
      .mockResolvedValueOnce(jsonResponse(payment))
      .mockResolvedValueOnce(jsonResponse({ assessment_id: 2, signals: [] }, 201))
      .mockResolvedValueOnce(jsonResponse({ assessment_id: 2, signals: [] }))
      .mockResolvedValueOnce({ ok: true, status: 204, text: vi.fn(), json: vi.fn() } as unknown as Response);

    await pullLatestCmsData();
    await getStoredPayments({ limit: 10, recipientState: 'OH' });
    await getStoredPayment('cms/record 1', '2025-07-24');
    await createRiskTriage('cms/record 1', '2025-07-24');
    await getCurrentRiskTriage('cms/record 1', '2025-07-24');
    await deleteStoredPayment('cms/record 1', '2025-07-24');

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      'http://localhost:8000/api/ingestions/cms',
      'http://localhost:8000/api/stored-payments?limit=10&recipient_state=OH',
      'http://localhost:8000/api/stored-payments/cms%2Frecord%201?payment_date=2025-07-24',
      'http://localhost:8000/api/stored-payments/cms%2Frecord%201/risk-triage?payment_date=2025-07-24',
      'http://localhost:8000/api/stored-payments/cms%2Frecord%201/risk-triage?payment_date=2025-07-24',
      'http://localhost:8000/api/stored-payments/cms%2Frecord%201?payment_date=2025-07-24',
    ]);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', body: JSON.stringify({ limit: 100, offset: 0 }) });
    expect(fetchMock.mock.calls[5][1]).toMatchObject({ method: 'DELETE' });
  });

  it('returns typed HTTP failures instead of replacing failed live data with mocks', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'not found' }, 404));

    await expect(getStoredPayment('missing', '2025-07-24')).rejects.toMatchObject<ApiError>({
      name: 'ApiError', status: 404,
    });
  });
});
