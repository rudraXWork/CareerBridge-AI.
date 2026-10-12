import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.nlp.resume_health import analyze_resume
from backend.services.resume_insights import generate_resume_insights, insight_context
from backend.services.web import ServiceError


@pytest.fixture
def review(candidate):
    return {'summary': 'Your dashboard shows practical Python and SQL work.',
            'strengths': ['You connect data preparation with reporting.'],
            'improvements': [{'statement_id': 'projects-1', 'title': 'Clarify the workflow',
                              'issue': 'Several steps are crowded into the same statement.',
                              'rewrite': 'Cleaned sales data using Python and Pandas, queried PostgreSQL with SQL, and built Power BI visualizations to compare monthly sales.',
                              'question': 'How did you check that the monthly comparisons were accurate?'}]}


def setup_provider(monkeypatch, review):
    monkeypatch.setenv('LLM_API_KEY', 'test-key')
    monkeypatch.setenv('LLM_MODEL', 'nvidia/nemotron-3.5-lightning-30b-a3b')
    monkeypatch.setenv('LLM_BASE_URL', 'https://integrate.api.nvidia.com/v1')
    calls = []

    def respond(*args, **kwargs):
        calls.append(kwargs['json'])
        return {'choices': [{'message': {'content': json.dumps(review)}}]}

    monkeypatch.setattr('backend.services.resume_insights.request_json', respond)
    return calls


def test_insights_link_to_original_without_changing_scores(candidate, review, monkeypatch):
    calls = setup_provider(monkeypatch, review)
    before = analyze_resume(candidate)
    result = TestClient(app).post('/resume/insights', json={'candidate': candidate.model_dump()})
    assert result.status_code == 200
    item = result.json()['insights']['improvements'][0]
    assert item['original'] == insight_context(candidate)['statements'][0]['text']
    assert item['section'] == 'projects'
    assert analyze_resume(candidate) == before
    context = json.loads(calls[0]['messages'][1]['content'])
    assert set(context) == {'skills', 'statements'}
    assert candidate.email not in json.dumps(context)
    assert candidate.name not in json.dumps(context)
    assert calls[0]['chat_template_kwargs']['enable_thinking'] is False


@pytest.mark.parametrize('fault', ['unknown_source', 'repeated_source', 'invented_number', 'missing_action'])
def test_rejects_unsupported_ai_reviews(candidate, review, monkeypatch, fault):
    item = review['improvements'][0]
    if fault == 'unknown_source':
        item['statement_id'] = 'projects-99'
    elif fault == 'repeated_source':
        review['improvements'].append(item.copy())
    elif fault == 'invented_number':
        item['rewrite'] += ' Saved 500 hours.'
    else:
        item['rewrite'] = ''
        item['question'] = ''
    setup_provider(monkeypatch, review)
    assert TestClient(app).post('/resume/insights', json={'candidate': candidate.model_dump()}).status_code == 503


def test_missing_configuration_and_empty_work_do_not_call_provider(candidate, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', '')
    monkeypatch.setattr('backend.services.resume_insights.request_json', lambda *a, **k: pytest.fail('No provider call expected'))
    with pytest.raises(ServiceError, match='Configure'):
        generate_resume_insights(candidate)
    candidate.projects = []
    candidate.experience = []
    with pytest.raises(ServiceError, match='Add project'):
        generate_resume_insights(candidate)


def test_provider_errors_do_not_return_fake_insights(candidate, review, monkeypatch):
    setup_provider(monkeypatch, review)

    def unavailable(*args, **kwargs):
        raise ServiceError('Resume AI returned HTTP 429. Check API access and quota.')

    monkeypatch.setattr('backend.services.resume_insights.request_json', unavailable)
    result = TestClient(app).post('/resume/insights', json={'candidate': candidate.model_dump()})
    assert result.status_code == 503
    assert '429' in result.json()['detail']
    assert 'insights' not in result.json()


def test_bad_model_json_is_a_recoverable_error(candidate, review, monkeypatch):
    setup_provider(monkeypatch, review)
    monkeypatch.setattr('backend.services.resume_insights.request_json', lambda *a, **k: {
        'choices': [{'message': {'content': 'not JSON'}}]})
    assert TestClient(app).post('/resume/insights', json={'candidate': candidate.model_dump()}).status_code == 503


def test_nvidia_gpt_oss_requests_the_insight_schema(candidate, review, monkeypatch):
    calls = setup_provider(monkeypatch, review)
    monkeypatch.setenv('LLM_MODEL', 'openai/gpt-oss-20b')
    assert generate_resume_insights(candidate)['model'] == 'openai/gpt-oss-20b'
    payload = calls[0]
    schema = payload['response_format']['json_schema']
    assert schema['strict'] is True
    assert schema['schema']['properties']['strengths']['maxItems'] == 3
    assert schema['schema']['properties']['improvements']['maxItems'] == 2
    item = schema['schema']['$defs']['ResumeInsight']
    assert set(item['required']) == set(item['properties'])
    assert payload['reasoning_effort'] == 'low'
    assert payload['max_tokens'] == 4096
    assert 'chat_template_kwargs' not in payload


def test_more_than_two_insights_are_rejected(candidate, review, monkeypatch):
    review['improvements'] *= 3
    setup_provider(monkeypatch, review)
    with pytest.raises(ServiceError, match='usable resume insights'):
        generate_resume_insights(candidate)


def test_truncated_insights_explain_incomplete_response(candidate, review, monkeypatch):
    setup_provider(monkeypatch, review)
    monkeypatch.setattr('backend.services.resume_insights.request_json', lambda *a, **k: {
        'choices': [{'finish_reason': 'length', 'message': {'content': '{'}}]})
    with pytest.raises(ServiceError, match='cut short'):
        generate_resume_insights(candidate)


@pytest.mark.parametrize('rewrite', [
    'Architecting a Rust/Tauri desktop application with Python inference, React and SQLite.',
    '  architecting a Rust/Tauri desktop application with Python inference, React and SQLite!  ',
    '',
])
def test_unchanged_wording_becomes_a_question_not_a_fake_rewrite(candidate, review, monkeypatch, rewrite):
    original = 'Architecting a Rust/Tauri desktop application with Python inference, React and SQLite.'
    candidate.projects = [original]
    review['improvements'][0].update(rewrite=rewrite, question='What is the application’s purpose and current stage?')
    setup_provider(monkeypatch, review)
    item = generate_resume_insights(candidate)['improvements'][0]
    assert item['original'] == original
    assert item['rewrite'] == ''
    assert item['rewrite_note']
    assert item['question'] == 'What is the application’s purpose and current stage?'


@pytest.mark.parametrize('original,rewrite', [
    ('Building a computer vision system that detects gestures through OBS.',
     'Built a computer vision system that detects gestures through OBS.'),
    ('Architecting a Rust/Tauri desktop application with Python inference.',
     'Designed a Rust/Tauri desktop application with Python inference.'),
    ('Currently developing a React interface for OBS controls.',
     'Developed a React interface for OBS controls.'),
])
def test_rewrite_cannot_claim_ongoing_work_is_finished(candidate, review, monkeypatch, original, rewrite):
    candidate.projects = [original]
    review['improvements'][0].update(rewrite=rewrite, question='Which parts are implemented so far?')
    setup_provider(monkeypatch, review)
    item = generate_resume_insights(candidate)['improvements'][0]
    assert item['rewrite'] == ''
    assert 'ongoing status' in item['rewrite_note']


def test_question_only_ai_insight_is_valid(candidate, review, monkeypatch):
    del review['improvements'][0]['rewrite']
    setup_provider(monkeypatch, review)
    item = generate_resume_insights(candidate)['improvements'][0]
    assert item['rewrite'] == ''
    assert item['question']


def test_distinct_rewrite_preserving_in_progress_status_is_kept(candidate, review, monkeypatch):
    candidate.projects = ['Building a Python system that detects gestures and triggers OBS overlays.']
    rewrite = 'Developing a Python gesture-detection system to trigger overlays in OBS.'
    review['improvements'][0].update(rewrite=rewrite, question='')
    setup_provider(monkeypatch, review)
    item = generate_resume_insights(candidate)['improvements'][0]
    assert item['rewrite'] == rewrite
    assert item['rewrite_note'] == ''


@pytest.mark.parametrize('rewrite,usable', [
    ('Built and benchmarked six regression models, selecting the Gradient Boosting model for deployment on Vercel and Render.', False),
    ('Benchmarked six regression models and deployed the best, a Gradient Boosting model with an R2 score of 96.06%, on Vercel and Render.', True),
])
def test_performance_rewrite_retains_reported_metric(candidate, review, monkeypatch, rewrite, usable):
    original = 'Built and benchmarked six regression models; deployed the best Gradient Boosting model with an R2 score of 96.06% on Vercel and Render.'
    candidate.projects = [original]
    review['improvements'][0].update(rewrite=rewrite, question='What was the validation split?')
    setup_provider(monkeypatch, review)
    item = generate_resume_insights(candidate)['improvements'][0]
    assert item['rewrite'] == (rewrite if usable else '')
    if not usable:
        assert 'metrics' in item['rewrite_note']
        assert item['original'] == original
        assert candidate.projects == [original]


def test_placeholder_metric_stays_a_question(candidate, review, monkeypatch):
    original = 'Delivered a market intelligence application with real-time dashboards.'
    candidate.projects = [original]
    review['improvements'][0].update(
        rewrite="Delivered a market intelligence application with real-time dashboards that reduced analysts' decision latency by X minutes.",
        question='What measurable benefit resulted from the dashboards?')
    setup_provider(monkeypatch, review)
    item = generate_resume_insights(candidate)['improvements'][0]
    assert item['rewrite'] == ''
    assert 'placeholder' in item['rewrite_note']
    assert item['question']
