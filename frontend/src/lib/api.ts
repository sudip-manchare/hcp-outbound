import type {
  DoctorListResponse,
  AuditCardData,
  SendAlertRequest,
  SendAlertResponse,
  DisputeNotice,
  NppesEnrichment,
  RiskTriageAssessment,
  CmsIngestionResult,
  CmsPaymentsPage,
  ServiceHealth,
  StoredPaymentRecord,
  StoredPaymentsPage,
} from './types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`API error ${status}: ${detail}`);
    this.name = 'ApiError';
  }
}

// ─── Utility ──────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function asNppesEnrichment(provider: {
  source: { retrieved_at: string };
  npi: string;
  status: string | null;
  legal_name: { first_name: string | null; last_name: string | null; credential: string | null; organization_name: string | null };
  primary_taxonomy: { code: string | null; description: string | null; license?: string | null; license_state?: string | null };
  practice_location: { address_1: string | null; address_2?: string | null; city: string | null; state: string | null; postal_code: string | null; telephone_number?: string | null };
  enumeration_date?: string | null;
  last_updated?: string | null;
  taxonomies?: { description: string | null }[];
}): NppesEnrichment {
  const firstName = provider.legal_name.first_name ?? '';
  const lastName = provider.legal_name.last_name ?? provider.legal_name.organization_name ?? '';
  return {
    npi: provider.npi,
    legal_name: [firstName, lastName, provider.legal_name.credential].filter(Boolean).join(' '),
    first_name: firstName,
    last_name: lastName,
    credential: provider.legal_name.credential ?? '',
    taxonomy_code: provider.primary_taxonomy.code ?? '',
    taxonomy_desc: provider.primary_taxonomy.description ?? '',
    primary_specialty: provider.primary_taxonomy.description ?? '',
    address: {
      address_1: [provider.practice_location.address_1, provider.practice_location.address_2].filter(Boolean).join(', '),
      city: provider.practice_location.city ?? '',
      state: provider.practice_location.state ?? '',
      postal_code: provider.practice_location.postal_code ?? '',
    },
    verified: provider.status === 'A',
    enriched_at: provider.source.retrieved_at,
    telephone_number: provider.practice_location.telephone_number ?? '',
    registry_status: provider.status ?? '',
    enumeration_date: provider.enumeration_date ?? '',
    last_updated: provider.last_updated ?? '',
    license_number: provider.primary_taxonomy.license ?? '',
    license_state: provider.primary_taxonomy.license_state ?? '',
    specialties: [...new Set((provider.taxonomies ?? []).map((item) => item.description).filter((value): value is string => Boolean(value)))],
  };
}

export function getHealth(): Promise<ServiceHealth> {
  return apiFetch<ServiceHealth>('/health');
}

export function getCmsPayments(params: {
  limit?: number; offset?: number; recipientState?: string; manufacturerId?: string; paymentNature?: string; recipientType?: string;
} = {}): Promise<CmsPaymentsPage> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.offset !== undefined) query.set('offset', String(params.offset));
  if (params.recipientState) query.set('recipient_state', params.recipientState);
  if (params.manufacturerId) query.set('manufacturer_id', params.manufacturerId);
  if (params.paymentNature) query.set('payment_nature', params.paymentNature);
  if (params.recipientType) query.set('recipient_type', params.recipientType);
  const suffix = query.size ? `?${query}` : '';
  return apiFetch<CmsPaymentsPage>(`/api/payments${suffix}`);
}

// ─── Physicians ───────────────────────────────────────────────────────────────

/**
 * Fetch the HCP roster from the retained CMS records.
 */
export function getDoctors(): Promise<DoctorListResponse> {
  return apiFetch<DoctorListResponse>('/api/doctors');
}

/**
 * Live NPPES NPI lookup — enriches a single physician record.
 */
export async function enrichNpi(npi: string): Promise<NppesEnrichment> {
  return asNppesEnrichment(await apiFetch<Parameters<typeof asNppesEnrichment>[0]>(`/api/doctors/enrich/${npi}`));
}

/**
 * Get audit card data for a specific physician.
 */
/** Get a token-scoped audit view from the backend. */
export function getAuditCardByToken(token: string): Promise<AuditCardData> {
  return apiFetch<AuditCardData>(`/api/audit/${encodeURIComponent(token)}`);
}

/**
 * Create an evidence-backed review-priority assessment for one locally stored
 * CMS payment. There is deliberately no mock fallback: an assessment must be
 * traceable to retained source data before it can be shown as an explanation.
 */
export async function createRiskTriage(
  recordId: string,
  paymentDate: string,
): Promise<RiskTriageAssessment> {
  const query = new URLSearchParams({ payment_date: paymentDate });
  return apiFetch<RiskTriageAssessment>(
    `/api/stored-payments/${encodeURIComponent(recordId)}/risk-triage?${query}`,
    { method: 'POST' },
  );
}

export function getCurrentRiskTriage(recordId: string, paymentDate: string): Promise<RiskTriageAssessment> {
  const query = new URLSearchParams({ payment_date: paymentDate });
  return apiFetch<RiskTriageAssessment>(`/api/stored-payments/${encodeURIComponent(recordId)}/risk-triage?${query}`);
}

export function getStoredPayments(params: { limit?: number; offset?: number; recipientState?: string } = {}): Promise<StoredPaymentsPage> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set('limit', String(params.limit));
  if (params.offset !== undefined) query.set('offset', String(params.offset));
  if (params.recipientState) query.set('recipient_state', params.recipientState);
  return apiFetch<StoredPaymentsPage>(`/api/stored-payments${query.size ? `?${query}` : ''}`);
}

export function getStoredPayment(recordId: string, paymentDate: string): Promise<StoredPaymentRecord> {
  const query = new URLSearchParams({ payment_date: paymentDate });
  return apiFetch<StoredPaymentRecord>(`/api/stored-payments/${encodeURIComponent(recordId)}?${query}`);
}

export function deleteStoredPayment(recordId: string, paymentDate: string): Promise<void> {
  const query = new URLSearchParams({ payment_date: paymentDate });
  return apiFetch<void>(`/api/stored-payments/${encodeURIComponent(recordId)}?${query}`, { method: 'DELETE' });
}

/** Pull one bounded, current CMS page into Tiger Data. */
export async function pullLatestCmsData(): Promise<CmsIngestionResult> {
  return apiFetch<CmsIngestionResult>('/api/ingestions/cms', {
    method: 'POST',
    body: JSON.stringify({ limit: 100, offset: 0 }),
  });
}

// ─── Campaign ─────────────────────────────────────────────────────────────────

/**
 * Send an outbound Sunshine Alert to a physician with secure 1-click audit link.
 */
export function sendAlert(req: SendAlertRequest): Promise<SendAlertResponse> {
  return apiFetch<SendAlertResponse>('/api/campaign/dispatch', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}


// ─── Dispute ──────────────────────────────────────────────────────────────────

/**
 * Generate a 42 CFR § 403.908 dispute notice.
 */
export function generateDispute(npi: string, auditToken: string): Promise<DisputeNotice> {
  return apiFetch<DisputeNotice>('/api/dispute/generate', {
    method: 'POST',
    body: JSON.stringify({ npi, audit_token: auditToken }),
  });
}

// ─── SSE Pipeline Events ──────────────────────────────────────────────────────

/**
 * Open a Server-Sent Events connection to the pipeline event stream.
 * Returns a cleanup function to close the connection.
 */
export function subscribeToPipelineEvents(
  onEvent: (type: string, data: unknown) => void,
): () => void {
  let es: EventSource | null = null;

  try {
    es = new EventSource(`${BASE_URL}/api/campaign/events`);
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data as string);
        onEvent((data as { type: string }).type, data);
      } catch {
        // ignore parse errors
      }
    };
    es.onerror = () => {
      // Connection failed — SSE not available in demo mode, ignore
      es?.close();
    };
  } catch {
    // EventSource not supported or server not running
  }

  return () => {
    es?.close();
  };
}

// ─── NPI Validation ───────────────────────────────────────────────────────────

/**
 * Validate NPI format: exactly 10 digits.
 */
export function isValidNpi(npi: string): boolean {
  return /^\d{10}$/.test(npi.trim());
}
