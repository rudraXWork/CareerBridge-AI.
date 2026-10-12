import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.company import domain_from_web
from backend.services.email_finder import resolve_company_domain
from backend.services.web import ServiceError


def official_result():
    return {'title': 'Deloitte media contacts', 'url': 'https://www.deloitte.com/us/en/contacts.html',
            'content': 'Media contacts: press@deloitte.com and team@deloitte.com'}


def test_multiple_regional_domains_use_official_web_evidence(monkeypatch):
    monkeypatch.setenv('HUNTER_API_KEY', 'test')
    monkeypatch.setattr('backend.services.email_finder.request_json', lambda *args, **kwargs: {
        'data': [{'company_name': 'Deloitte', 'domain': 'deloitte.com'},
                 {'company_name': 'Deloitte', 'domain': 'deloitte.co.uk'}]})
    monkeypatch.setattr('backend.services.company.search_web', lambda *args: [official_result()])
    domain, source = resolve_company_domain('deloitte')
    assert domain == 'deloitte.com' and 'https://www.deloitte.com/' in source


@pytest.mark.parametrize('hunter_key', ['', 'test'])
def test_web_fallback_works_without_hunter_or_after_provider_failure(monkeypatch, hunter_key):
    monkeypatch.setenv('HUNTER_API_KEY', hunter_key)

    def unavailable(*args, **kwargs):
        raise ServiceError('Hunter quota unavailable')

    monkeypatch.setattr('backend.services.email_finder.request_json', unavailable)
    monkeypatch.setattr('backend.services.company.search_web', lambda *args: [official_result()])
    assert resolve_company_domain('Deloitte')[0] == 'deloitte.com'


def test_job_boards_social_pages_and_lookalike_domains_are_not_company_domains(monkeypatch):
    rows = [{'title': 'Deloitte company emails', 'url': f'https://{host}/deloitte',
             'content': 'Deloitte hiring: recruiter@example.com'}
            for host in ['linkedin.com', 'jobs.example.com', 'deloitte.example.com', 'notdeloitte.com']]
    monkeypatch.setattr('backend.services.company.search_web', lambda *args: rows)
    assert domain_from_web('Deloitte') == ('', '')


def test_country_domain_and_company_initials(monkeypatch):
    monkeypatch.setattr('backend.services.company.search_web', lambda *args: [{
        'title': 'Tata Consultancy Services contacts', 'url': 'https://www.tcs.co.uk/contact',
        'content': 'Tata Consultancy Services: careers@tcs.co.uk'}])
    assert domain_from_web('Tata Consultancy Services')[0] == 'tcs.co.uk'


def test_company_website_without_email_is_a_domain_lead(monkeypatch):
    monkeypatch.setattr('backend.services.company.search_web', lambda *args: [{
        'title': 'Acme official website', 'url': 'https://www.acme.com', 'content': 'Acme company information'}])
    assert domain_from_web('Acme')[0] == 'acme.com'


def test_ambiguous_sources_do_not_invent_company_domain(monkeypatch):
    monkeypatch.setattr('backend.services.company.search_web', lambda *args: [
        {'title': 'Acme contacts', 'url': 'https://acme.com', 'content': 'Acme careers'},
        {'title': 'Acme contacts', 'url': 'https://acme.co.uk', 'content': 'Acme careers'}])
    assert not domain_from_web('Acme')[0]


def test_missing_domain_warns_once_and_retries_do_not_accumulate_notes(monkeypatch):
    monkeypatch.setattr('backend.routes.contacts.resolve_company_domain', lambda *args: ('', 'Automatic search unavailable'))
    monkeypatch.setattr('backend.routes.contacts.find_email', lambda *args: pytest.fail('Do not repeat failed domain checks for every person'))
    data = {'company': 'Deloitte', 'target_role': 'Consulting', 'find_email': True,
            'person': {'name': 'William Ha', 'company': 'Deloitte', 'role': 'Consulting Manager',
                       'profile_url': 'https://www.linkedin.com/in/example', 'evidence': 'William — manager at Deloitte',
                       'email_source': 'User supplied', 'warnings': ['Supply the company’s real email domain for email discovery.'] * 6}}
    client = TestClient(app)
    for _ in range(2):
        response = client.post('/contacts/find', json=data).json()
        assert response['warnings'] == ['Automatic search unavailable']
        contact = response['contacts'][0]
        assert len(contact['warnings']) == 1
        assert contact['email_source'] == ''
        data['person'] = contact


def test_resolved_domain_flows_into_patterns_without_manual_input(monkeypatch):
    monkeypatch.setattr('backend.services.company.search_web', lambda *args: [official_result()])
    monkeypatch.setattr('backend.services.email_finder.email_checks', lambda *args: {'syntax': True, 'mx_records': True})
    client = TestClient(app)
    data = {'company': 'Deloitte', 'target_role': 'Consulting', 'find_email': True, 'allow_patterns': True,
            'person': {'name': 'William Ha', 'company': 'Deloitte', 'role': 'Consulting Manager'}}
    response = client.post('/contacts/find', json=data).json()
    contact = response['contacts'][0]
    assert response['company_domain'] == 'deloitte.com'
    assert contact['email'] == 'william.ha@deloitte.com'
    assert contact['email_status'] == 'Inferred'
    assert contact['email_checks']['domain_source'].startswith('Public company source: https://www.deloitte.com/')
