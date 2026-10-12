import json

import httpx
import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import Contact, ContactRequest, JobInput
from backend.services.email_finder import find_email, provider_status
from backend.services.employee_search import contacts_from_page, rank_contact
from backend.services.job_search import discover_jobs, resolve_job
from backend.services.llm import build_context, generate_email
from backend.services.web import ServiceError, request_json, structured_items, validate_public_url


def test_contact_ranking():
    manager = rank_contact(Contact(role='Data Science Manager'), 'Data Scientist')
    recruiter = rank_contact(Contact(role='Technical Recruiter'), 'Data Scientist')
    unrelated = rank_contact(Contact(role='Marketing Manager'), 'Data Scientist')
    assert manager.relevance_score > recruiter.relevance_score > unrelated.relevance_score
    assert 0 <= unrelated.relevance_score <= 100


def test_person_sources_need_company_attribution():
    items = [{'@type': 'Person', 'name': 'Asha Rao', 'jobTitle': 'Data Manager', 'worksFor': {'name': 'Demo'},
              'email': 'mailto:asha@example.com'},
             {'@type': 'Person', 'name': 'Someone Else', 'jobTitle': 'Data Manager', 'worksFor': {'name': 'Other'}}]
    soup = BeautifulSoup('<script type="application/ld+json">' + json.dumps(items) + '</script>', 'html.parser')
    people = contacts_from_page(soup, 'Demo', 'https://example.com/team')
    assert len(people) == 1 and people[0].name == 'Asha Rao'
    assert people[0].email_status == 'Public' and people[0].email == 'asha@example.com'
    assert len(list(structured_items(soup, 'Person'))) == 2


def test_no_keys_no_invented_results(monkeypatch, candidate):
    client = TestClient(app)
    assert client.post('/jobs/search', json={'candidate': candidate.model_dump(), 'target_role': 'Analyst'}).status_code == 503
    assert client.post('/contacts/find', json={'company': 'Demo', 'target_role': 'Analyst'}).status_code == 503


def test_direct_person_skips_search_and_providers(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Direct person/email must skip discovery and provider lookups')

    monkeypatch.setattr('backend.routes.contacts.discover_contacts', forbidden)
    monkeypatch.setattr('backend.services.email_finder.hunter_lookup', forbidden)
    monkeypatch.setattr('backend.services.email_finder.apollo_lookup', forbidden)
    monkeypatch.setattr('backend.services.email_finder.email_checks', lambda *args: {'syntax': True})
    request = ContactRequest(company='Demo', target_role='Data Analyst', find_email=True,
                             person=Contact(name='Rahul Sharma', company='Demo', email='rahul@example.com',
                                            email_status='Verified'))
    result = TestClient(app).post('/contacts/find', json=request.model_dump())
    assert result.status_code == 200
    assert result.json()['contacts'][0]['email_status'] == 'Unknown'


def test_hunter_apollo_and_patterns(monkeypatch):
    monkeypatch.setattr('backend.services.email_finder.email_checks', lambda *args: {'syntax': True, 'mx_records': True})
    contact = Contact(name='Rahul Sharma', company='Demo')
    patterns = find_email(contact, 'example.com', allow_patterns=True)
    assert patterns.email_status == 'Inferred'
    assert len(patterns.inferred_emails) == 3
    assert patterns.confidence is None
    monkeypatch.setattr('backend.services.email_finder.hunter_lookup',
                        lambda *args: {'email': 'rahul@example.com', 'score': 98, 'verification': {'status': 'valid'}})
    found = find_email(contact, 'example.com')
    assert found.email_status == 'Verified' and found.email_source == 'Hunter'
    assert provider_status('accept_all') == 'Likely'

    def hunter_failure(*args):
        raise ServiceError('Hunter quota unavailable')

    monkeypatch.setattr('backend.services.email_finder.hunter_lookup', hunter_failure)
    monkeypatch.setattr('backend.services.email_finder.apollo_lookup',
                        lambda *args: {'email': 'rahul@example.com', 'email_status': 'verified'})
    fallback = find_email(contact, 'example.com')
    assert fallback.email_source == 'Apollo'
    assert fallback.warnings


def test_job_schema_and_supplied_description(monkeypatch, candidate):
    schema = {'@type': 'JobPosting', 'title': 'Data Analyst', 'hiringOrganization': {'name': 'Demo'},
              'description': '<p>Python and SQL required.</p>'}
    soup = BeautifulSoup('<script type="application/ld+json">' + json.dumps(schema) + '</script>', 'html.parser')
    monkeypatch.setattr('backend.services.job_search.fetch_page', lambda url: (soup, url))
    monkeypatch.setattr('backend.services.job_search.search_web',
                        lambda *args: [{'url': 'https://example.com/job'}])
    from backend.models import JobSearchRequest
    jobs, warnings = discover_jobs(JobSearchRequest(candidate=candidate, target_role='Data Analyst'))
    assert len(jobs) == 1 and jobs[0].company == 'Demo'
    assert 'Python' in jobs[0].job_description
    monkeypatch.setattr('backend.services.job_search.fetch_page', lambda url: pytest.fail('Supplied JD should be used directly'))
    supplied = JobInput(company='Demo', role='Analyst', job_description='My actual description')
    assert resolve_job(supplied) == supplied


def test_empty_discovery_returns_partial_results(monkeypatch, candidate):
    from backend.models import JobSearchRequest
    monkeypatch.setattr('backend.services.job_search.search_web', lambda *args: [])
    jobs, warnings = discover_jobs(JobSearchRequest(candidate=candidate, target_role='Analyst'))
    assert jobs == [] and warnings


def test_private_urls_rejected(monkeypatch):
    monkeypatch.setattr('socket.getaddrinfo', lambda *args, **kwargs: [(2, 1, 6, '', ('127.0.0.1', 80))])
    with pytest.raises(ServiceError):
        validate_public_url('http://localhost/job')
    with pytest.raises(ServiceError):
        validate_public_url('file:///etc/passwd')


def test_provider_errors_do_not_leak_keys(monkeypatch):
    request = httpx.Request('GET', 'https://api.example.com?api_key=secret')
    response = httpx.Response(401, request=request)
    monkeypatch.setattr(httpx, 'request', lambda *args, **kwargs: response)
    with pytest.raises(ServiceError) as error:
        request_json('GET', str(request.url), 'Provider')
    assert 'secret' not in str(error.value) and '401' in str(error.value)


def test_llm_structured_context_and_output(monkeypatch, candidate, jobs):
    from backend.nlp.job_parser import parse_job
    from backend.nlp.matcher import match_resume
    monkeypatch.setattr('backend.nlp.matcher.similarities', lambda texts, target: [0.8] * len(texts))
    job = parse_job(JobInput(**jobs[0]))
    match = match_resume(candidate, job)
    context = build_context(candidate, job, match, Contact(name='Rahul Sharma'), '', 'Professional')
    assert 'email' not in context['candidate']
    assert 'sections' not in context['candidate']
    assert context['match']['score'] == match.score
    with pytest.raises(ServiceError, match='Fill LLM'):
        generate_email(context)
    monkeypatch.setenv('LLM_API_KEY', 'test-key')
    monkeypatch.setenv('LLM_BASE_URL', 'https://api.example.com/v1')
    monkeypatch.setenv('LLM_MODEL', 'test-model')
    body = ('Hi Rahul, I am Asha Rao, a computer science student interested in the Data Analyst Intern role at '
            'Demo Analytics (fictional classroom example). I have used Python, SQL and Power BI in my sales dashboard '
            'project to clean data, compare monthly sales and build visual reports. My academic work has given me '
            'practice querying PostgreSQL and working with Pandas. I would like to learn how your analytics team '
            'approaches reporting and whether there might be a suitable internship opportunity. Would you be open '
            'to a short conversation or point me toward the right contact? Thank you, Asha Rao')
    draft = {'subject': 'Data Analyst Intern inquiry', 'body': body}
    monkeypatch.setattr('backend.services.llm.request_json',
                        lambda *args, **kwargs: {'choices': [{'message': {'content': json.dumps(draft)}}]})
    assert generate_email(context).body == body
    monkeypatch.setattr('backend.services.llm.request_json',
                        lambda *args, **kwargs: {'choices': [{'message': {'content': json.dumps({**draft, 'word_count': 118})}}]})
    assert generate_email(context).model_dump() == draft
    # A broad networking interest need not appear as an exact job title.
    context['job']['role'] = 'Data Science and Analytics'
    context['purpose'] = 'Networking'
    assert generate_email(context).body == body
    context['purpose'] = 'Job application'
    with pytest.raises(ServiceError, match='omitted the company or role'):
        generate_email(context)
    context['purpose'] = 'Referral'
    context['job']['company'] = 'Another company'
    with pytest.raises(ServiceError, match='omitted the company or role'):
        generate_email(context)
    monkeypatch.setattr('backend.services.llm.request_json',
                        lambda *args, **kwargs: {'choices': [{'message': {'content': '{}'}}]})
    with pytest.raises(ServiceError):
        generate_email(context)


def test_api_upload_match_and_storage(candidate, jobs, monkeypatch, tmp_path):
    monkeypatch.setattr('backend.nlp.matcher.similarities', lambda texts, target: [0.8] * len(texts))
    client = TestClient(app)
    resume = (candidate.name + '\nSKILLS\nPython SQL').encode()
    uploaded = client.post('/resume/upload', files={'file': ('resume.txt', resume, 'text/plain')})
    assert uploaded.status_code == 200
    assert uploaded.json()['profile']['name'] == candidate.name
    assert client.post('/resume/upload', files={'file': ('bad.pdf', b'bad', 'application/pdf')}).status_code == 422
    result = client.post('/match', json={'candidate': candidate.model_dump(), 'job': jobs[0]})
    assert result.status_code == 200 and result.json()['match']['score'] is not None
    assert result.json()['id']
    # A selected analyzed job can be passed straight to the next step.
    reused = client.post('/match', json={'candidate': candidate.model_dump(), 'job': result.json()['job']})
    assert reused.status_code == 200 and reused.json()['match']['score'] == result.json()['match']['score']
    assert client.get('/health').status_code == 200


def test_email_endpoint_uses_local_match_and_skips_contacts(candidate, jobs, monkeypatch):
    from backend.models import GeneratedEmail
    monkeypatch.setattr('backend.nlp.matcher.similarities', lambda texts, target: [0.8] * len(texts))

    def forbidden(*args, **kwargs):
        pytest.fail('Email generation must not discover employees or email addresses')

    monkeypatch.setattr('backend.routes.contacts.discover_contacts', forbidden)
    monkeypatch.setattr('backend.services.email_finder.hunter_lookup', forbidden)
    seen = []

    def generate(context):
        seen.append(context)
        return GeneratedEmail(subject='Inquiry', body='Test email from mocked LLM')

    monkeypatch.setattr('backend.routes.email.generate_email', generate)
    payload = {'candidate': candidate.model_dump(), 'job': jobs[0],
               'employee': {'name': 'Rahul Sharma', 'company': jobs[0]['company'], 'email': 'rahul@example.com'},
               'tone': 'Technical'}
    result = TestClient(app).post('/email/generate', json=payload)
    assert result.status_code == 200
    assert seen[0]['match']['score'] == result.json()['match']['score']
    assert seen[0]['tone'] == 'Technical'
    payload['employee']['company'] = 'Another company'
    assert TestClient(app).post('/email/generate', json=payload).status_code == 422
    assert len(seen) == 1


@pytest.mark.parametrize('purpose', ['Networking', 'Referral'])
def test_company_outreach_without_listing_or_matching(candidate, monkeypatch, purpose):
    from backend.models import Contact, GeneratedEmail

    def forbidden(*args, **kwargs):
        pytest.fail('Company outreach must not search for jobs or calculate a match')

    monkeypatch.setattr('backend.routes.email.match_resume', forbidden)
    monkeypatch.setattr('backend.services.job_search.search_web', forbidden)
    monkeypatch.setattr('backend.routes.contacts.discover_contacts',
                        lambda company, role, limit: ([Contact(name='Maya Rao', company=company,
                                                               role='Data Manager', email='maya@example.com')], [], []))
    seen = []

    def generate(context):
        seen.append(context)
        return GeneratedEmail(subject='Career advice', body='Fictional mocked introduction')

    monkeypatch.setattr('backend.routes.email.generate_email', generate)
    client = TestClient(app)
    people = client.post('/contacts/find', json={'company': 'Demo Analytics', 'target_role': 'Data Analyst'})
    assert people.status_code == 200
    employee = people.json()['contacts'][0]
    result = client.post('/email/generate', json={'candidate': candidate.model_dump(),
                        'job': {'company': 'Demo Analytics', 'role': 'Data Analyst'},
                        'employee': employee, 'purpose': purpose})
    assert result.status_code == 200
    assert result.json()['match'] is None
    assert seen[0]['match'] is None
    assert seen[0]['job']['description_available'] is False
    assert seen[0]['candidate']['relevant_projects'] == candidate.projects[:2]
    assert seen[0]['purpose'] == purpose


def test_low_match_does_not_block_email(candidate, jobs, monkeypatch):
    from backend.models import GeneratedEmail, MatchResult
    monkeypatch.setattr('backend.routes.email.match_resume', lambda *args: MatchResult(score=5))
    monkeypatch.setattr('backend.routes.email.generate_email',
                        lambda context: GeneratedEmail(subject='Introduction', body='Fictional mocked introduction'))
    result = TestClient(app).post('/email/generate', json={'candidate': candidate.model_dump(),
                                 'job': jobs[0], 'employee': {'name': 'Maya Rao'}, 'purpose': 'Referral'})
    assert result.status_code == 200
    assert result.json()['match']['score'] == 5
