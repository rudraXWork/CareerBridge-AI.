import json
from datetime import datetime, timedelta, timezone

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import CandidateProfile, JobSearchRequest, MatchResult
from backend.services.job_search import discover_jobs, job_from_index, job_from_schema, search_queries
from backend.services.web import ServiceError, search_web


def posting(n=0, days=1, expires=10):
    today = datetime.now(timezone.utc).date()
    return {'@type': 'JobPosting', 'title': f'Junior Data Analyst {n}',
            'hiringOrganization': {'name': f'Company {n}'},
            'description': 'Requirements: Python and SQL. ' + 'Analyze data and build useful dashboards for our clients. ' * 5,
            'datePosted': str(today - timedelta(days=days)),
            'validThrough': str(today + timedelta(days=expires))}


def soup_for(items):
    return BeautifulSoup('<script type="application/ld+json">' + json.dumps(items) + '</script>', 'html.parser')


def test_resume_queries_need_no_company_and_do_not_share_identity(candidate):
    candidate.name = 'Private Student'
    candidate.email = 'private@example.com'
    queries = search_queries(JobSearchRequest(candidate=candidate))
    assert 1 <= len(queries) <= 3
    assert any('SQL' in query for query in queries)
    assert all(any(skill in query for skill in candidate.normalized_skills) and 'job opening' in query for query in queries)
    assert not any(candidate.name in query or candidate.email in query for query in queries)
    explicit = search_queries(JobSearchRequest(candidate=candidate, target_role='Frontend Developer',
                                              company='Demo', location='Remote'))
    assert len(explicit) == 1 and 'Frontend Developer' in explicit[0] and 'Demo Remote' in explicit[0]


def test_empty_profile_needs_evidence_not_invented_roles():
    with pytest.raises(ServiceError, match='Review your resume skills'):
        search_queries(JobSearchRequest(candidate=CandidateProfile()))


def test_tavily_receives_date_filter(monkeypatch):
    seen = []
    monkeypatch.setenv('TAVILY_API_KEY', 'test-key')
    monkeypatch.setattr('backend.services.web.request_json', lambda *args, **kw: seen.append(kw['json']) or {'results': []})
    search_web('Python jobs', 10, time_range='month')
    assert seen[0]['time_range'] == 'month' and seen[0]['max_results'] == 10
    search_web('Python jobs', 10, time_range='month', job_search=True)
    assert seen[1]['include_raw_content'] == 'text' and seen[1]['search_depth'] == 'advanced'
    assert 'linkedin.com/jobs/view' in seen[1]['include_domains']
    search_web('Company employees')
    assert 'time_range' not in seen[2] and not seen[2]['include_raw_content']


def test_discovery_fetches_more_candidates_and_filters_old_expired_future(monkeypatch, candidate):
    calls = []

    def search(query, limit, **kw):
        calls.append((query, limit, kw))
        return [{'url': f'https://example.com/jobs/{n}'} for n in range(8)]

    items = [posting(n) for n in range(8)]
    items[0] = posting(0, days=60)
    items[1] = posting(1, expires=-1)
    items[2] = posting(2, days=-1)
    monkeypatch.setattr('backend.services.job_search.search_web', search)
    monkeypatch.setattr('backend.services.job_search.fetch_page',
                        lambda url: (soup_for(items[int(url.rsplit('/', 1)[-1])]), url))
    found, warnings = discover_jobs(JobSearchRequest(candidate=candidate))
    assert len(found) == 5
    assert {job.company for job in found} == {f'Company {n}' for n in range(3, 8)}
    assert all(limit == 10 and kw['time_range'] == 'month' for _, limit, kw in calls)
    assert not warnings


def test_public_linkedin_description_without_schema(monkeypatch, candidate):
    html = '''<h1 class="top-card-layout__title">Data Analyst</h1>
        <a class="topcard__org-name-link">Demo</a><span class="topcard__flavor--bullet">Remote</span>
        <div class="description__text">''' + posting()['description'] + '</div>'
    monkeypatch.setattr('backend.services.job_search.search_web', lambda *args, **kw: [{'url': 'https://example.com/jobs/1'}])
    monkeypatch.setattr('backend.services.job_search.fetch_page', lambda url: (BeautifulSoup(html, 'html.parser'), url))
    found, _ = discover_jobs(JobSearchRequest(candidate=candidate))
    assert len(found) == 1 and found[0].company == 'Demo'
    assert found[0].posted_at == '' and found[0].source == 'Public job page'
    monkeypatch.setattr('backend.services.job_search.fetch_page',
                        lambda url: (BeautifulSoup(html + '<p>No longer accepting applications</p>', 'html.parser'), url))
    assert discover_jobs(JobSearchRequest(candidate=candidate))[0] == []


def test_search_snippets_are_not_scored_as_full_jobs(monkeypatch, candidate):
    monkeypatch.setattr('backend.services.job_search.search_web', lambda *args, **kw: [
        {'url': 'https://example.com/jobs', 'title': '100 jobs hiring', 'content': posting()['description']}])
    monkeypatch.setattr('backend.services.job_search.fetch_page',
                        lambda url: (BeautifulSoup('<h1>Find jobs</h1>', 'html.parser'), url))
    assert discover_jobs(JobSearchRequest(candidate=candidate))[0] == []
    assert job_from_schema(posting(expires=-1), 'https://example.com/job') is None


def test_indexed_description_requires_identity_and_substantive_job_text():
    result = {'url': 'https://www.linkedin.com/jobs/view/data-analyst-at-demo-123?tracking=abc',
              'title': 'Demo hiring Data Analyst in Remote | LinkedIn',
              'raw_content': 'Data Analyst\nDemo Remote 2 days ago\nReport this job\n' +
              posting()['description'] * 2 + '\nSeniority level\nEntry level\nSimilar jobs\nJava Docker'}
    job = job_from_index(result)
    assert job.company == 'Demo' and job.role == 'Data Analyst'
    assert '?' not in job.job_url and 'Java Docker' not in job.job_description
    assert 'opening unconfirmed' in job.source
    assert job.posted_at
    assert job_from_index({**result, 'raw_content': 'short search snippet'}) is None
    assert job_from_index({**result, 'title': 'Unknown hiring Data Analyst in Remote'}) is None
    assert job_from_index({**result, 'url': 'https://www.linkedin.com/jobs/search/'}) is None
    assert job_from_index({**result, 'raw_content': result['raw_content'] + '\nNo longer accepting applications'}) is None


def test_linkedin_uses_indexed_description_without_repeated_blocked_fetches(monkeypatch, candidate):
    result = {'url': 'https://www.linkedin.com/jobs/view/data-analyst-at-demo-123',
              'title': 'Data Analyst at Demo — Remote | LinkedIn Jobs',
              'raw_content': 'Data Analyst\nDemo\nReport this job\n' + posting()['description'] * 2}
    monkeypatch.setattr('backend.services.job_search.search_web', lambda *args, **kw: [result])

    def blocked(url):
        pytest.fail('Indexed LinkedIn descriptions do not need another blocked page request')

    monkeypatch.setattr('backend.services.job_search.fetch_page', blocked)
    jobs, warnings = discover_jobs(JobSearchRequest(candidate=candidate))
    assert len(jobs) == 1 and jobs[0].company == 'Demo' and not warnings
    monkeypatch.setattr('backend.services.job_search.search_web', lambda *args, **kw: [{**result, 'raw_content': None}])
    assert discover_jobs(JobSearchRequest(candidate=candidate))[0] == []


def test_enough_complete_indexed_jobs_skip_slow_extra_pages(monkeypatch, candidate):
    results = [{'url': f'https://www.linkedin.com/jobs/view/data-analyst-{n}',
                'title': f'Demo {n} hiring Data Analyst in Remote | LinkedIn',
                'raw_content': f'Demo {n}\nData Analyst\nReport this job\n' + posting()['description'] * 2}
               for n in range(6)]
    results.append({'url': 'https://example.com/slow-page'})
    monkeypatch.setattr('backend.services.job_search.search_web', lambda *args, **kw: results)
    monkeypatch.setattr('backend.services.job_search.fetch_page', lambda url: pytest.fail('Enough indexed descriptions already available'))
    jobs, warnings = discover_jobs(JobSearchRequest(candidate=candidate))
    assert len(jobs) == 6 and not warnings


def test_api_ranks_all_results_before_selecting_five(monkeypatch, candidate):
    jobs = [job_from_schema(posting(n), f'https://example.com/jobs/{n}') for n in range(8)]
    monkeypatch.setattr('backend.routes.jobs.discover_jobs', lambda req: (jobs, []))
    monkeypatch.setattr('backend.routes.jobs.match_resume',
                        lambda candidate, job: MatchResult(score=float(job.role.rsplit(' ', 1)[-1]) * 10))
    result = TestClient(app).post('/jobs/search', json={'candidate': candidate.model_dump()})
    assert result.status_code == 200
    assert [item['match']['score'] for item in result.json()['opportunities']] == [70, 60, 50, 40, 30]
    assert 'not hiring probabilities' in result.json()['note']


def test_partial_results_and_missing_key_are_explicit(monkeypatch, candidate):
    client = TestClient(app)
    assert client.post('/jobs/search', json={'candidate': candidate.model_dump()}).status_code == 503
    monkeypatch.setattr('backend.routes.jobs.discover_jobs', lambda req: ([], []))
    result = client.post('/jobs/search', json={'candidate': candidate.model_dump()}).json()
    assert result['opportunities'] == [] and 'aiming for 5' in result['warnings'][0]
