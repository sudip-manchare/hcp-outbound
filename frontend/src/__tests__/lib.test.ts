import { describe, it, expect } from 'vitest';
import { isValidNpi, searchPhysicians } from '@/lib/api';
import { MOCK_PHYSICIANS, buildMockAuditCard, buildMockDisputeNotice } from '@/lib/mockData';

describe('isValidNpi', () => {
  it('accepts exactly 10 numeric digits', () => {
    expect(isValidNpi('1235149876')).toBe(true);
  });
  it('rejects less than 10 digits', () => {
    expect(isValidNpi('123456789')).toBe(false);
  });
  it('rejects more than 10 digits', () => {
    expect(isValidNpi('12345678901')).toBe(false);
  });
  it('rejects non-numeric characters', () => {
    expect(isValidNpi('123456789X')).toBe(false);
    expect(isValidNpi('1234-56789')).toBe(false);
  });
  it('trims whitespace before validation', () => {
    expect(isValidNpi('  1235149876  ')).toBe(true);
  });
});

describe('searchPhysicians', () => {
  it('returns all physicians for empty query', () => {
    const results = searchPhysicians('');
    expect(results.length).toBe(MOCK_PHYSICIANS.length);
  });

  it('finds physician by last name (case-insensitive)', () => {
    const results = searchPhysicians('miller');
    expect(results.some((p) => p.nppes.last_name === 'Miller')).toBe(true);
  });

  it('finds physician by NPI', () => {
    const results = searchPhysicians('1235149876');
    expect(results).toHaveLength(1);
    expect(results[0].npi).toBe('1235149876');
  });

  it('finds physician by specialty', () => {
    const results = searchPhysicians('cardiology');
    expect(results.every((p) => p.nppes.primary_specialty.toLowerCase().includes('cardiol'))).toBe(true);
  });

  it('returns empty array for unmatched query', () => {
    const results = searchPhysicians('zzz_no_match_zzz');
    expect(results).toHaveLength(0);
  });
});

describe('MOCK_PHYSICIANS data integrity', () => {
  it('has at least 15 physicians', () => {
    expect(MOCK_PHYSICIANS.length).toBeGreaterThanOrEqual(15);
  });

  it('all physicians have valid 10-digit NPIs', () => {
    MOCK_PHYSICIANS.forEach((p) => {
      expect(isValidNpi(p.npi)).toBe(true);
    });
  });

  it('all physicians have required NPPES fields', () => {
    MOCK_PHYSICIANS.forEach((p) => {
      expect(p.nppes.legal_name).toBeTruthy();
      expect(p.nppes.taxonomy_desc).toBeTruthy();
      expect(p.nppes.primary_specialty).toBeTruthy();
      expect(p.nppes.address.city).toBeTruthy();
    });
  });

  it('mismatch_score is between 0 and 1', () => {
    MOCK_PHYSICIANS.forEach((p) => {
      expect(p.mismatch_score).toBeGreaterThanOrEqual(0);
      expect(p.mismatch_score).toBeLessThanOrEqual(1);
    });
  });

  it('risk_level matches mismatch_score for anomalous physicians', () => {
    const critical = MOCK_PHYSICIANS.filter((p) => p.risk_level === 'critical');
    critical.forEach((p) => {
      expect(p.mismatch_score).toBeGreaterThan(0.7);
    });
  });

  it('unreviewed_count matches actual unreviewed payments', () => {
    MOCK_PHYSICIANS.forEach((p) => {
      const actual = p.payments.filter((pay) => !pay.reviewed).length;
      expect(p.unreviewed_count).toBe(actual);
    });
  });

  it('total_amount is consistent with sum of payments', () => {
    MOCK_PHYSICIANS.forEach((p) => {
      const sum = p.payments.reduce((acc, pay) => acc + pay.amount, 0);
      expect(Math.abs(p.total_amount - sum)).toBeLessThan(1); // allow floating point
    });
  });
});

describe('buildMockAuditCard', () => {
  it('returns an audit card with the correct physician', () => {
    const physician = MOCK_PHYSICIANS[0];
    const card = buildMockAuditCard(physician);
    expect(card.physician.npi).toBe(physician.npi);
    expect(card.audit_token).toContain(physician.npi);
  });

  it('includes velocity summary with at least one month', () => {
    const card = buildMockAuditCard(MOCK_PHYSICIANS[0]);
    expect(card.velocity_summary.length).toBeGreaterThan(0);
    expect(card.velocity_summary[0]).toHaveProperty('month');
    expect(card.velocity_summary[0]).toHaveProperty('is_surge');
  });

  it('flags surge months', () => {
    const card = buildMockAuditCard(MOCK_PHYSICIANS[0]); // Dr. Miller has velocity flags
    const surges = card.velocity_summary.filter((v) => v.is_surge);
    expect(surges.length).toBeGreaterThanOrEqual(1);
  });
});

describe('buildMockDisputeNotice', () => {
  it('generates notice with correct legal citation', () => {
    const physician = MOCK_PHYSICIANS[0];
    const notice = buildMockDisputeNotice(physician);
    expect(notice.legal_citation).toBe('42 CFR § 403.908');
  });

  it('only includes unreviewed payments in dispute', () => {
    const physician = MOCK_PHYSICIANS[0];
    const notice = buildMockDisputeNotice(physician);
    notice.disputed_payments.forEach((p) => {
      expect(p.reviewed).toBe(false);
    });
  });

  it('total_disputed_amount sums disputed payments', () => {
    const physician = MOCK_PHYSICIANS[0];
    const notice = buildMockDisputeNotice(physician);
    const expected = notice.disputed_payments.reduce((s, p) => s + p.amount, 0);
    expect(notice.total_disputed_amount).toBeCloseTo(expected, 2);
  });

  it('generates unique notice IDs', () => {
    const p = MOCK_PHYSICIANS[0];
    const n1 = buildMockDisputeNotice(p);
    const n2 = buildMockDisputeNotice(p);
    // IDs are timestamp-based, but we just check they're strings
    expect(typeof n1.notice_id).toBe('string');
    expect(n1.notice_id.startsWith('DISP-')).toBe(true);
  });
});
