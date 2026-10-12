import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import Contact
from backend.services.company import company_name
from backend.services.email_finder import company_pattern, find_email, pattern_emails, resolve_company_domain
from backend.services.employee_search import contact_from_snippet, contact_from_title, discover_contacts
from backend.services.web import ServiceError


def result(name='Digna Tarver', content='Current role: Global Business Talent Acquisition Manager at HPE'):
    return {'title': f'{name} - Global Business Talent Acquisition Manager at ...',
            'url': 'https://www.linkedin.com/in/person', 'content': content}


def test_hpe_alias_is_not_hp():
    assert company_name('HPE') == company_name('Hewlett Packard Enterprise')
    assert company_name('HP') != company_name('HPE')
    assert company_name('HP Inc.') != company_name('HPE')


def test_current_role_snippet_recovers_truncated_title():
    contact = contact_from_snippet(result(), 'Hewlett Packard Enterprise')
    assert contact.name == 'Digna Tarver'
    assert contact.role == 'Global Business Talent Acquisition Manager'
    assert contact.source == 'Public search snippet'
    assert contact.evidence and contact.profile_url


def test_current_experience_recovers_role_without_company():
    content = ('## Experience\n- TA Operations Program Manager at Hewlett Packard Enterprise (Dec 2025 to present)\n'
               '- Recruiter at Another Company (Jan 2022 to Jan 2024) [...] Headline: Manager at HPE\n'
               'Current role: TA Operations Program Manager')
    contact = contact_from_snippet(result('Samantha White', content), 'HPE')
    assert contact.role == 'TA Operations Program Manager'


@pytest.mark.parametrize('content', [
    'Headline: Recruiter at HPE\nCurrent role: Recruiter at HP Inc.',
    'Headline: Recruiter at HPE\nCurrent role: Recruiter\n## Experience\n- Recruiter at Allstate (May 2026 to present)',
    'Headline: Former Recruiter at HPE',
    '# Someone Else\nCurrent role: Recruiter at HPE',
])
def test_other_employer_and_stale_headline_rejected(content):
    assert contact_from_snippet(result(content=content), 'HPE') is None


def test_titles_need_employer_attribution():
    assert contact_from_title({'title': 'Asha Rao - Technical Consultant at Hewlett Packard Enterprise | LinkedIn'}, 'HPE')
    assert contact_from_title({'title': 'Asha Rao - Technical Recruiter - HPE'}, 'HPE')
    assert contact_from_title({'title': 'Asha R. Rao - Technical Recruiter - HPE'}, 'HPE')
    assert contact_from_title({'title': 'Asha Rao - Recruiter at HP Inc. | HPE Careers'}, 'HPE') is None
    assert contact_from_title({'title': 'Asha Rao - Former Recruiter - HPE'}, 'HPE') is None
    assert contact_from_title({'title': 'A.R. - Manager - HPE'}, 'HPE') is None


def test_discovery_searches_hr_and_team_and_deduplicates(monkeypatch):
    queries = []

    def search(query, limit):
        queries.append(query)
        return [result()]

    monkeypatch.setattr('backend.services.employee_search.search_web', search)
    monkeypatch.setattr('backend.services.employee_search.fetch_page', lambda *args: pytest.fail('Do not crawl blocked profiles'))
    contacts, types, warnings = discover_contacts('HPE', 'Technology Consulting', 5)
    assert len(contacts) == 1 and contacts[0].name == 'Digna Tarver'
    assert len(queries) == 2
    assert 'Technology Consulting' in queries[0] and 'talent acquisition' in queries[1]
    assert all('Hewlett Packard Enterprise' in query for query in queries)
    assert types and not warnings


def test_partial_search_failure_preserves_people(monkeypatch):
    def search(query, limit):
        if 'talent acquisition' in query:
            raise ServiceError('Search unavailable')
        return [result()]

    monkeypatch.setattr('backend.services.employee_search.search_web', search)
    contacts, _, warnings = discover_contacts('HPE', 'Technology Consulting', 5)
    assert contacts and 'Search unavailable' in warnings


def test_stale_title_cannot_override_new_employer(monkeypatch):
    row = result(content='Current role: Recruiter at Other Company')
    row['title'] = 'Digna Tarver - Recruiter at HPE | LinkedIn'
    monkeypatch.setattr('backend.services.employee_search.search_web', lambda *args: [row])
    contacts, _, warnings = discover_contacts('HPE', 'Technology Consulting', 5)
    assert not contacts and warnings


def test_domain_lookup_requires_unambiguous_company(monkeypatch):
    monkeypatch.setenv('HUNTER_API_KEY', 'test')
    monkeypatch.setattr('backend.services.email_finder.request_json', lambda *args, **kwargs: {
        'data': [{'company_name': 'Demo', 'domain': 'example.com'}]})
    assert resolve_company_domain('Demo')[0] == 'example.com'
    assert not resolve_company_domain('Other')[0]
    monkeypatch.setattr('backend.services.email_finder.request_json', lambda *args, **kwargs: {
        'data': [{'company_name': 'Demo', 'domain': 'one.example'}, {'company_name': 'Demo', 'domain': 'two.example'}]})
    assert not resolve_company_domain('Demo')[0]
    assert resolve_company_domain('HPE')[0] == 'hpe.com'


@pytest.mark.parametrize('statuses, expected, address', [
    (['invalid', 'valid'], 'Verified', 'asha@example.com'),
    (['accept_all'], 'Likely', 'asha.rao@example.com'),
    (['unknown'], 'Inferred', 'asha.rao@example.com'),
    (['invalid', 'invalid', 'invalid'], 'Unknown', ''),
])
def test_patterns_are_verified_and_invalid_addresses_skipped(monkeypatch, statuses, expected, address):
    monkeypatch.setattr('backend.services.email_finder.email_checks', lambda *args: {'syntax': True, 'mx_records': True})
    monkeypatch.setattr('backend.services.email_finder.hunter_lookup', lambda *args: None)
    monkeypatch.setattr('backend.services.email_finder.apollo_lookup', lambda *args: None)
    calls = []

    def verify(email):
        calls.append(email)
        return {'status': statuses[len(calls) - 1]}

    monkeypatch.setattr('backend.services.email_finder.verify_email', verify)
    found = find_email(Contact(name='Asha Rao'), 'example.com', True)
    assert found.email_status == expected and found.email == address
    assert len(calls) == len(statuses)
    assert found.email_checks['pattern_checks'][calls[0]] == statuses[0]


def test_invalid_finder_address_uses_fallback(monkeypatch):
    monkeypatch.setattr('backend.services.email_finder.email_checks', lambda *args: {'syntax': True})
    monkeypatch.setattr('backend.services.email_finder.hunter_lookup', lambda *args: {
        'email': 'bad@example.com', 'verification': {'status': 'invalid'}})
    monkeypatch.setattr('backend.services.email_finder.apollo_lookup', lambda *args: {
        'email': 'asha@example.com', 'email_status': 'verified'})
    found = find_email(Contact(name='Asha Rao'), 'example.com')
    assert found.email == 'asha@example.com' and found.email_source == 'Apollo'


def test_verifier_unavailable_does_not_confirm_pattern(monkeypatch):
    monkeypatch.setattr('backend.services.email_finder.email_checks', lambda *args: {'syntax': True, 'mx_records': True})
    monkeypatch.setattr('backend.services.email_finder.hunter_lookup', lambda *args: None)
    monkeypatch.setattr('backend.services.email_finder.apollo_lookup', lambda *args: None)

    def unavailable(email):
        raise ServiceError('Hunter verifier unavailable')

    monkeypatch.setattr('backend.services.email_finder.verify_email', unavailable)
    found = find_email(Contact(name='Asha Rao'), 'example.com', True)
    assert found.email_status == 'Inferred'
    assert found.email_checks['pattern_checks'][found.email] == 'unverified'
    assert 'Hunter verifier unavailable' in found.warnings


def test_observed_company_pattern_is_tried_first():
    guesses = pattern_emails('Asha Rao', 'example.com', '{first}_{last}')
    assert guesses[0] == 'asha_rao@example.com'
    assert len(guesses) == 4
    assert len(pattern_emails('Asha Rao', 'example.com', '{first}.{last}')) == 3
    assert pattern_emails('Asha Rao', 'example.com', '{unsupported}') == pattern_emails('Asha Rao', 'example.com')


@pytest.mark.parametrize('data, expected', [
    ({'domain': 'example.com', 'pattern': '{first}_{last}'}, '{first}_{last}'),
    ({'domain': None, 'pattern': None}, ''),
    ({'domain': 'other.com', 'pattern': '{first}'}, ''),
])
def test_company_pattern_needs_matching_domain(monkeypatch, data, expected):
    monkeypatch.setenv('HUNTER_API_KEY', 'test')
    monkeypatch.setattr('backend.services.email_finder.request_json', lambda *args, **kwargs: {'data': data})
    assert company_pattern('example.com') == expected


def test_fallback_checks_observed_pattern_before_common_guesses(monkeypatch):
    monkeypatch.setattr('backend.services.email_finder.email_checks', lambda *args: {'syntax': True, 'mx_records': True})
    monkeypatch.setattr('backend.services.email_finder.hunter_lookup', lambda *args: None)
    monkeypatch.setattr('backend.services.email_finder.apollo_lookup', lambda *args: None)
    monkeypatch.setattr('backend.services.email_finder.company_pattern', lambda domain: '{first}_{last}')
    calls = []
    monkeypatch.setattr('backend.services.email_finder.verify_email', lambda email: calls.append(email) or {'status': 'valid'})
    found = find_email(Contact(name='Asha Rao'), 'example.com', True)
    assert calls == ['asha_rao@example.com']
    assert found.email == 'asha_rao@example.com' and found.email_status == 'Verified'
    assert found.email_checks['pattern_source'] == 'Hunter Domain Search'


def test_contact_route_resolves_domain_only_when_email_requested(monkeypatch):
    monkeypatch.setattr('backend.routes.contacts.discover_contacts', lambda *args: ([Contact(name='Asha Rao')], [], []))
    calls = []
    monkeypatch.setattr('backend.routes.contacts.resolve_company_domain', lambda company: (calls.append(company) or 'example.com', 'Hunter'))
    monkeypatch.setattr('backend.services.email_finder.email_checks', lambda *args: {'syntax': True})
    client = TestClient(app)
    data = {'company': 'Demo', 'target_role': 'Analyst'}
    assert client.post('/contacts/find', json=data).status_code == 200
    assert not calls
    response = client.post('/contacts/find', json={**data, 'find_email': True, 'allow_patterns': True}).json()
    assert calls == ['Demo'] and response['company_domain'] == 'example.com'
    assert response['contacts'][0]['email_status'] == 'Inferred'
