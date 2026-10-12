from datetime import datetime, timezone

from bs4 import BeautifulSoup

from backend.models import JobInput
from backend.services.web import ServiceError, fetch_page, page_text, search_web, structured_items


def job_from_schema(item, url):
    company = item.get('hiringOrganization') or {}
    if not isinstance(company, dict):
        return None
    role = item.get('title') or item.get('name', '')
    description = BeautifulSoup(item.get('description', ''), 'html.parser').get_text('\n', strip=True)
    if not role or not company.get('name') or not description:
        return None
    expires = item.get('validThrough')
    if expires:
        try:
            if datetime.fromisoformat(expires.replace('Z', '+00:00')).date() < datetime.now(timezone.utc).date():
                return None
        except (ValueError, AttributeError):
            pass
    locations = item.get('jobLocation') or []
    locations = locations if isinstance(locations, list) else [locations]
    names = []
    for loc in locations:
        address = loc.get('address', {}) if isinstance(loc, dict) else {}
        if isinstance(address, dict):
            names.append(', '.join(str(address[k]) for k in ('addressLocality', 'addressRegion', 'addressCountry')
                                   if address.get(k)))
    return JobInput(company=company['name'], role=role, location='; '.join(filter(None, names)),
                    job_url=url, job_description=description[:50_000], source='Public JobPosting metadata')


def resolve_job(job):
    if job.job_description.strip() or not job.job_url:
        return job
    soup, url = fetch_page(job.job_url)
    for item in structured_items(soup, 'JobPosting'):
        found = job_from_schema(item, url)
        if found:
            return found
    if not job.company or not job.role:
        raise ServiceError('No structured job found. Supply the company, role and full description.')
    return JobInput(**{**job.model_dump(include=set(JobInput.model_fields)), 'job_url': url, 'job_description': page_text(soup),
                       'source': 'Public page; user supplied company and role'})


def discover_jobs(request):
    query = ' '.join(filter(None, [request.target_role, request.company, request.location, request.job_type,
                                  'job careers description requirements']))
    jobs, warnings, seen = [], [], set()
    results = search_web(query, request.limit)
    for result in results:
        url = result.get('url', '')
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            soup, final_url = fetch_page(url)
            found = [job_from_schema(item, final_url) for item in structured_items(soup, 'JobPosting')]
            for job in found:
                if job and (not request.company or request.company.casefold() in job.company.casefold()):
                    jobs.append(job)
        except ServiceError as exc:
            warnings.append(f'{url}: {exc}')
    if not jobs:
        warnings.append('No readable, structured job listings were found. Supply a job URL or description directly.')
    unique = {(job.job_url, job.company, job.role): job for job in jobs}
    return list(unique.values())[:request.limit], warnings
