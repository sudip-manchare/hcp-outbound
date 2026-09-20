import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.services import gemini_explanation_service as service


def assessment():
    return {
        'assessment_id': 7, 'model_version': 'isolation-forest-v2',
        'risk_score': 98, 'risk_level': 'high_priority_review', 'review_recommended': True,
        'plain_language_explanation': 'Unusual among retained payments.',
        'model_metadata': {'isolation_forest_prediction': 'outlier', 'anomaly_percentile': 98},
        'signals': [{'code': 'amount', 'evidence': {'value': 5000, 'dataset_median': 20}}],
        'payment': {'raw_cms_record_id': 'cms-123', 'payment_date': '2025-07-24',
                    'amount_usd': '5000', 'recipient_specialty': 'Cardiology',
                    'payment_type': 'Consulting Fee', 'manufacturer_name': 'Example',
                    'recipient_npi': '1234567890', 'raw_payload': 'not sent'},
    }


def analysis():
    return {
        'summary': 'This reported consulting payment warrants comparison with the agreement.',
        'isolation_forest_interpretation': 'The stored model classifies it as an outlier, not proven wrongdoing.',
        'qualitative_context': ['Consulting payments may cover professional services.'],
        'possible_benign_explanations': ['The amount might reflect multiple services.'],
        'suggested_checks': ['Compare the amount with the consulting agreement.'],
        'limitations': ['The agreement and service details were not supplied.'],
    }


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    config = SimpleNamespace(GEMINI_API_KEY='test-secret', GEMINI_MODEL='gemini-2.5-flash', GEMINI_TIMEOUT_SECONDS=1)
    monkeypatch.setattr(service, 'get_settings', lambda: config)
    return config


def call_with_response(handler):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await service.explain_assessment(assessment(), client)
    return asyncio.run(run())


def test_sends_selected_payment_and_exact_stored_model_evidence():
    def handler(request):
        assert request.headers['x-goog-api-key'] == 'test-secret'
        assert 'test-secret' not in str(request.url)
        body = json.loads(request.content)
        context = json.loads(body['contents'][0]['parts'][0]['text'])
        assert context['payment']['raw_cms_record_id'] == 'cms-123'
        assert context['payment']['amount_usd'] == '5000'
        assert 'recipient_npi' not in context['payment']
        assert 'raw_payload' not in context['payment']
        assert context['isolation_forest']['model_metadata'] == assessment()['model_metadata']
        assert context['isolation_forest']['signals'] == assessment()['signals']
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(analysis())}]}}]})
    result = call_with_response(handler)
    assert result['status'] == 'generated'
    assert result['assessment_id'] == 7
    assert result['record_id'] == 'cms-123'
    assert result['analysis'] == analysis()


@pytest.mark.parametrize('payload', [
    {}, {'candidates': []},
    {'candidates': [{'finishReason': 'SAFETY'}]},
    {'candidates': [{'finishReason': 'MAX_TOKENS'}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'not json'}]}}]},
    {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"summary": "incomplete"}'}]}}]},
])
def test_rejects_blocked_incomplete_or_invalid_outputs(payload):
    result = call_with_response(lambda _: httpx.Response(200, json=payload))
    assert result['status'] == 'unavailable'
    assert 'analysis' not in result


@pytest.mark.parametrize('status', [401, 429, 500])
def test_upstream_failures_do_not_leak_response_body(status):
    result = call_with_response(lambda _: httpx.Response(status, text='test-secret'))
    assert result['status'] == 'unavailable'
    assert 'test-secret' not in json.dumps(result)


def test_timeout_returns_unavailable():
    def handler(request):
        raise httpx.ReadTimeout('timeout', request=request)
    assert call_with_response(handler)['status'] == 'unavailable'


def test_missing_key_skips_network(settings):
    settings.GEMINI_API_KEY = ''
    def handler(_):
        pytest.fail('must not call Gemini without a key')
    assert call_with_response(handler)['status'] == 'not_configured'
