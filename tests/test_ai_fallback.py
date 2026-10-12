import json

import pytest

from backend.services.llm import generate_email
from backend.services.resume_insights import generate_resume_insights
from backend.services.web import ServiceError


@pytest.fixture(params=['insights', 'email'])
def ai_case(request, candidate):
    if request.param == 'insights':
        result = {'summary': 'The resume includes practical data analysis work.',
                  'strengths': ['The project uses Python and SQL.'],
                  'improvements': [{'statement_id': 'projects-1', 'title': 'Explain the result',
                                    'issue': 'The statement does not explain how the analysis was used.',
                                    'rewrite': '', 'question': 'What decision did the analysis support?'}]}
        return generate_resume_insights, candidate, result, 'resume_insights'
    context = {'job': {'company': 'Demo Analytics', 'role': 'Data Analyst'}, 'purpose': 'Networking'}
    body = ('Hi Taylor, I am a computer science student interested in learning about Demo Analytics. '
            'My sales dashboard project gave me practice cleaning data with Python, querying it with SQL, '
            'and creating charts to compare monthly trends. I would appreciate hearing how your team '
            'approaches reporting and what skills a student should develop before applying for analytics roles. '
            'If you have time, would you be open to a short conversation or suggest someone I could contact '
            'for career advice? Thank you for considering my request. Best regards, Alex')
    return generate_email, context, {'subject': 'Learning about analytics work', 'body': body}, 'llm'


def mock_ai(monkeypatch, case, respond, groq_key='groq-test-key'):
    monkeypatch.setenv('LLM_API_KEY', 'nvidia-test-key')
    monkeypatch.setenv('LLM_BASE_URL', 'https://integrate.api.nvidia.com/v1')
    monkeypatch.setenv('LLM_MODEL', 'openai/gpt-oss-20b')
    monkeypatch.setenv('GROQ_API_KEY', groq_key)
    monkeypatch.setattr(f'backend.services.{case[3]}.request_json', respond)


@pytest.mark.parametrize('fault', ['quota', 'unavailable', 'timeout', 'bad_json'])
def test_primary_failure_uses_groq_with_same_context(ai_case, monkeypatch, fault):
    generate, context, result, kind = ai_case
    calls = []

    def respond(method, url, provider, **kwargs):
        calls.append((url, kwargs))
        if len(calls) == 1:
            if fault == 'bad_json':
                return {'choices': [{'message': {'content': 'not JSON'}}]}
            raise ServiceError({'quota': 'HTTP 429', 'unavailable': 'HTTP 503',
                                'timeout': 'Provider request timed out'}[fault])
        return {'choices': [{'message': {'content': json.dumps(result)}}]}

    mock_ai(monkeypatch, ai_case, respond)
    output = generate(context)
    assert len(calls) == 2
    assert calls[1][0] == 'https://api.groq.com/openai/v1/chat/completions'
    assert calls[0][1]['headers']['Authorization'] == 'Bearer nvidia-test-key'
    assert calls[1][1]['headers']['Authorization'] == 'Bearer groq-test-key'
    payload = calls[1][1]['json']
    assert payload['messages'] == calls[0][1]['json']['messages']
    assert payload['model'] == 'openai/gpt-oss-120b'
    assert payload['reasoning_effort'] == 'low'
    assert 'chat_template_kwargs' not in payload
    if kind == 'resume_insights':
        assert payload['response_format']['json_schema']['strict'] is True
        assert output['model'] == 'openai/gpt-oss-120b'
    else:
        assert output.body == result['body']


def test_successful_primary_does_not_call_groq(ai_case, monkeypatch):
    calls = []

    def respond(*args, **kwargs):
        calls.append(args[1])
        return {'choices': [{'message': {'content': json.dumps(ai_case[2])}}]}

    mock_ai(monkeypatch, ai_case, respond)
    ai_case[0](ai_case[1])
    assert calls == ['https://integrate.api.nvidia.com/v1/chat/completions']


@pytest.mark.parametrize('key', ['', 'your_groq_key'])
def test_missing_groq_key_preserves_primary_error(ai_case, monkeypatch, key):
    calls = []

    def respond(*args, **kwargs):
        calls.append(args[1])
        raise ServiceError('HTTP 429')

    mock_ai(monkeypatch, ai_case, respond, key)
    with pytest.raises(ServiceError, match='^HTTP 429$'):
        ai_case[0](ai_case[1])
    assert len(calls) == 1


def test_both_provider_failures_stop_after_two_attempts(ai_case, monkeypatch):
    calls = []

    def respond(*args, **kwargs):
        calls.append(args[1])
        raise ServiceError('HTTP 503')

    mock_ai(monkeypatch, ai_case, respond)
    with pytest.raises(ServiceError, match='Groq fallback failed') as error:
        ai_case[0](ai_case[1])
    assert len(calls) == 2
    assert 'nvidia-test-key' not in str(error.value)
    assert 'groq-test-key' not in str(error.value)


def test_fallback_also_rejects_unsupported_resume_claims(candidate, monkeypatch):
    case = (generate_resume_insights, candidate, None, 'resume_insights')

    def respond(method, url, provider, **kwargs):
        if 'nvidia.com' in url:
            raise ServiceError('HTTP 503')
        result = {'summary': 'Data work.', 'strengths': [], 'improvements': [{
            'statement_id': 'projects-99', 'title': 'Unsupported source', 'issue': 'Test',
            'rewrite': '', 'question': 'What was the result?'}]}
        return {'choices': [{'message': {'content': json.dumps(result)}}]}

    mock_ai(monkeypatch, case, respond)
    with pytest.raises(ServiceError, match='unsupported statements'):
        generate_resume_insights(candidate)
