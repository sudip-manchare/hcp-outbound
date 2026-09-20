// ─── Core Domain Types ───────────────────────────────────────────────────────

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface NppesAddress {
  address_1: string;
  city: string;
  state: string;
  postal_code: string;
}

export interface NppesEnrichment {
  npi: string;
  legal_name: string;
  first_name: string;
  last_name: string;
  credential: string; // MD, DO, etc.
  taxonomy_code: string;
  taxonomy_desc: string;
  primary_specialty: string;
  address: NppesAddress;
  verified: boolean;
  enriched_at: string; // ISO timestamp
  telephone_number?: string;
  registry_status?: string;
  enumeration_date?: string;
  last_updated?: string;
  license_number?: string;
  license_state?: string;
  specialties?: string[];
}

export interface CmsPayment {
  id: string;
  payment_date: string;
  manufacturer: string;
  nature_of_payment: string; // 'Food and Beverage', 'Consulting Fee', etc.
  amount: number;
  product_name: string;
  product_category: string;
  reviewed: boolean;
  mismatch_score: number; // 0.0–1.0 from pgvector cosine distance
  risk_score?: number; // non-zero only when the current Isolation Forest batch flags it
  velocity_flag: boolean; // from TimescaleDB time_bucket surge detection
}

// ─── Explainable risk triage ────────────────────────────────────────────────

export type TriageRiskLevel = 'low' | 'review' | 'high_priority_review';

export interface RiskSignal {
  code: string;
  weight: number;
  title: string;
  plain_explanation: string;
  evidence: Record<string, unknown>;
}

/** A grounded explanation returned by the backend—not free-form model output. */
export interface RiskTriageAssessment {
  assessment_id: number;
  assessed_at: string;
  model_version: string;
  risk_score: number;
  risk_level: TriageRiskLevel;
  review_recommended: boolean;
  plain_language_explanation: string;
  signals: RiskSignal[];
  payment?: { raw_cms_record_id: string; payment_date: string };
  ai_explanation?: {
    provider: 'gemini';
    model: string;
    status: 'generated' | 'not_configured' | 'unavailable';
    message?: string;
    analysis?: {
      summary: string;
      isolation_forest_interpretation: string;
      qualitative_context: string[];
      possible_benign_explanations: string[];
      suggested_checks: string[];
      limitations: string[];
    };
  };
}

export interface CmsIngestionResult {
  run_id: number;
  records_seen: number;
  records_inserted: number;
  records_skipped: number;
  risk_assessments_invalidated: number;
  risk_assessments_created: number;
  risk_assessments_flagged: number;
  risk_model_version: string;
  pagination: { next_offset: number | null };
}

export interface ServiceHealth {
  status: 'ok';
  sources: {
    nppes: string;
    cms_open_payments: string;
    cms_dataset_id: string;
  };
}

export interface CmsPaymentsPage {
  source: Record<string, unknown>;
  filters: Record<string, string>;
  pagination: {
    limit: number;
    offset: number;
    total_matching_records: number;
    returned_records: number;
    next_offset: number | null;
  };
  payments: Array<Record<string, unknown>>;
}

/** The immutable CMS fields plus the local review annotations returned by storage routes. */
export interface StoredPaymentRecord {
  raw_cms_record_id: string;
  payment_date: string;
  recipient_npi: string | null;
  recipient_state: string | null;
  manufacturer_name: string;
  payment_type: string | null;
  amount_usd: string | number;
  is_reviewed: boolean;
  mismatch_score: number | null;
  [field: string]: unknown;
}

export interface StoredPaymentsPage {
  pagination: {
    limit: number;
    offset: number;
    total_records: number;
    returned_records: number;
    next_offset: number | null;
  };
  records: StoredPaymentRecord[];
}

export interface Physician {
  npi: string;
  nppes: NppesEnrichment;
  payments: CmsPayment[];
  // Computed aggregates
  total_amount: number;
  meal_count: number;
  unreviewed_count: number;
  outlier_count?: number;
  mismatch_score: number; // max mismatch across payments
  risk_score?: number; // max current explainable triage score across payments
  risk_level: RiskLevel;
  // Tiger Data metadata
  timescale_latency_ms?: number;
  pgvector_calcs?: number;
}

// ─── API Response Types ───────────────────────────────────────────────────────

export interface DoctorListResponse {
  physicians: Physician[];
  total: number;
  tiger_data_metrics: TigerDataMetrics;
}

export interface AuditCardData {
  physician: Physician;
  audit_token: string;
  generated_at: string;
  velocity_summary: VelocitySummary[];
  top_manufacturers: ManufacturerSummary[];
}

export interface VelocitySummary {
  month: string; // '2024-12'
  payment_count: number;
  total_amount: number;
  is_surge: boolean; // TimescaleDB flagged
}

export interface ManufacturerSummary {
  name: string;
  total_amount: number;
  payment_count: number;
}

export interface DisputeNotice {
  physician_name: string;
  physician_npi: string;
  physician_credential: string;
  physician_specialty: string;
  physician_address: string;
  manufacturer_name: string;
  manufacturer_contact: string;
  disputed_payments: CmsPayment[];
  total_disputed_amount: number;
  legal_citation: string; // "42 CFR § 403.908"
  generated_at: string;
  notice_id: string;
}

// ─── Campaign / Pipeline Types ────────────────────────────────────────────────

export interface CampaignMetrics {
  dispatched: number;
  opened: number;
  disputed: number;
  claimed: number;
}

export interface SendAlertRequest {
  npi: string;
  channel?: 'portal_link' | 'email';
}

export interface SendAlertResponse {
  success: boolean;
  audit_token: string;
  audit_url: string;
  message: string;
  simulated: boolean;
}

// ─── Tiger Data Live Metrics ──────────────────────────────────────────────────

export interface TigerDataMetrics {
  timescale_query_ms: number;
  pgvector_calcs: number;
  hypertable_chunks: number;
  vector_index_type: 'hnsw' | 'ivfflat';
  active_physicians: number;
  total_payments: number;
}

// ─── Portal & Workspace State ─────────────────────────────────────────────────

export type PortalStep = 'audit' | 'notice' | 'enrolled';

export interface AuditWorkspaceState {
  step: PortalStep;
  selectedPhysician: Physician | null;
  auditToken: string | null;
  disputeNotice: DisputeNotice | null;
  isLoading: boolean;
  error: string | null;
}

// ─── SSE Event Types ──────────────────────────────────────────────────────────

export type PipelineEventType =
  | 'alert_dispatched'
  | 'audit_opened'
  | 'dispute_submitted'
  | 'enrollment_confirmed';

export interface PipelineEvent {
  type: PipelineEventType;
  npi: string;
  physician_name: string;
  timestamp: string;
}
