import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { RiskExplanationCard } from '@/components/RiskExplanationCard';
import type { RiskTriageAssessment } from '@/lib/types';

const assessment: RiskTriageAssessment = {
  assessment_id: 7, assessed_at: '2026-09-19', model_version: 'isolation-forest-v2',
  risk_score: 98, risk_level: 'high_priority_review', review_recommended: true,
  plain_language_explanation: 'Stored Isolation Forest result.', signals: [],
  payment: { raw_cms_record_id: 'cms-123', payment_date: '2025-07-24' },
};

afterEach(cleanup);

it('shows Gemini interpretation alongside the original score and record identity', () => {
  render(<RiskExplanationCard assessment={{ ...assessment, ai_explanation: {
    provider: 'gemini', model: 'gemini-2.5-flash', status: 'generated', analysis: {
      summary: 'Compare the reported payment with the agreement.',
      isolation_forest_interpretation: 'The model flagged an unusual combination.',
      qualitative_context: ['Consulting payments may cover professional services.'],
      possible_benign_explanations: ['Multiple services may be included.'],
      suggested_checks: ['Check the invoice.'], limitations: ['The agreement was not supplied.'],
    },
  } }} />);
  expect(screen.getByText('CMS record cms-123')).toBeInTheDocument();
  expect(screen.getByText(/98\/100/)).toBeInTheDocument();
  expect(screen.getByText('Stored Isolation Forest result.')).toBeInTheDocument();
  expect(screen.getByText('Gemini qualitative analysis')).toBeInTheDocument();
  expect(screen.getByText('Check the invoice.')).toBeInTheDocument();
});

it('preserves the model explanation when Gemini is unavailable', () => {
  render(<RiskExplanationCard assessment={{ ...assessment, ai_explanation: {
    provider: 'gemini', model: 'gemini-2.5-flash', status: 'unavailable', message: 'Gemini is temporarily unavailable.',
  } }} />);
  expect(screen.getByRole('status')).toHaveTextContent('Gemini is temporarily unavailable.');
  expect(screen.getByText('Stored Isolation Forest result.')).toBeInTheDocument();
  expect(screen.queryByText('Gemini qualitative analysis')).not.toBeInTheDocument();
});
