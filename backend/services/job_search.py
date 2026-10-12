import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from backend.models import JobInput
from backend.nlp.skills import ROLE_SKILLS, suggest_roles
from backend.services.web import ServiceError, fetch_page, page_text, search_web, structured_items


def date_value(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date()
    except (ValueError, AttributeError, TypeError):
        return None


def job_from_schema(item, url):
    company = item.get('hiringOrganization') or {}
    if not isinstance(company, dict):
        return None
    role = item.get('title') or item.get('name', '')
    description = BeautifulSoup(item.get('description', ''), 'html.parser').get_text('\n', strip=True)
    if not role or not company.get('name') or not description:
        return None
    expires = item.get('validThrough')
    if date_value(expires) and date_value(expires) < datetime.now(timezone.utc).date():
        return None
    locations = item.get('jobLocation') or []
    locations = locations if isinstance(locations, list) else [locations]
    names = []
    for loc in locations:
        address = loc.get('address', {}) if isinstance(loc, dict) else {}
        if isinstance(address, dict):
            names.append(', '.join(str(address[k]) for k in ('addressLocality', 'addressRegion', 'addressCountry')
                                   if address.get(k)))
    return JobInput(company=company['name'], role=role, location='; '.join(filter(None, names)),
                    job_url=url, job_description=description[:50_000], source='Public JobPosting metadata',
                    posted_at=str(item.get('datePosted') or ''), valid_through=str(expires or ''))


def job_from_page(soup, url):
    # Public LinkedIn pages expose these fields even without JSON-LD.
    role = soup.select_one('.top-card-layout__title, [itemprop="title"]')
    company = soup.select_one('.topcard__org-name-link, [itemprop="hiringOrganization"]')
    description = soup.select_one('.description__text, [itemprop="description"]')
    if not role or not company or not description:
        return None
    text = description.get_text('\n', strip=True)
    if len(text.split()) < 30 or re.search(r'job (?:is no longer available|has expired)|no longer accepting applications',
                                         page_text(soup), re.I):
        return None
    location = soup.select_one('.topcard__flavor--bullet, [itemprop="jobLocation"]')
    date = soup.select_one('time[datetime]')
    return JobInput(role=role.get_text(' ', strip=True), company=company.get_text(' ', strip=True),
                    job_description=text[:50_000], job_url=url,
                    location=location.get_text(' ', strip=True) if location else '',
                    posted_at=date.get('datetime', '') if date else '', source='Public job page')


def job_from_index(result):
    url, text = result.get('url', ''), result.get('raw_content') or ''
    parts = urlsplit(url)
    if parts.hostname not in ('www.linkedin.com', 'linkedin.com') or not parts.path.startswith('/jobs/view/'):
        return None
    title = re.sub(r'\s*\|\s*LinkedIn(?: Jobs)?$', '', result.get('title', ''), flags=re.I)
    found = re.fullmatch(r'(.+?) hiring (.+?) in (.+)', title)
    if found:
        company, role, location = found.groups()
    else:
        found = re.fullmatch(r'(.+?) at (.+?) [—–] (.+)', title)
        if found:
            role, company, location = found.groups()
        else:
            found = re.fullmatch(r'(.+?) - (.+)', title)
            if not found:
                return None
            role, company = found.groups()
            location = ''
    if company.casefold() not in text.casefold() or role.casefold() not in text.casefold():
        return None
    if re.search(r'no longer accepting applications|job (?:is no longer available|has expired)', text, re.I):
        return None
    # Ignore sign-in prompts and related-job lists in indexed LinkedIn pages.
    description = re.split(r'About the job|Report this job', text, maxsplit=1, flags=re.I)
    if len(description) != 2:
        return None
    description = re.split(r'Seniority level|Show less|Similar jobs', description[1], maxsplit=1, flags=re.I)[0].strip()
    if len(description.split()) < 80 or not re.search(r'requirements|qualifications|responsibilities|skills|experience', description, re.I):
        return None
    posted = ''
    age = re.search(r'\b(\d+)\s+(hour|day|week|month)s? ago\b', text[:4000], re.I)
    if age:
        days = int(age[1]) * {'hour': 0, 'day': 1, 'week': 7, 'month': 30}[age[2].lower()]
        posted = str(datetime.now(timezone.utc).date() - timedelta(days=days))
    return JobInput(company=company, role=role, location=location,
                    job_url=urlunsplit((parts.scheme, parts.netloc, parts.path, '', '')),
                    job_description=description[:50_000], posted_at=posted,
                    source='Tavily indexed job description; opening unconfirmed')


def search_queries(request):
    skills = request.candidate.normalized_skills
    roles = [request.target_role] if request.target_role else (
        request.candidate.possible_roles[:3] or suggest_roles(request.candidate.normalized_skills))
    if not roles and not skills:
        raise ServiceError('Review your resume skills or add an optional target role before searching.')
    level = ''
    if not request.target_role and (request.candidate.experience_years == 0 or (
            request.candidate.experience_years is None and not request.candidate.experience)):
        level = 'entry level'
    return [' '.join(filter(None, [role, ' '.join(sorted(skills,
                                   key=lambda skill: ROLE_SKILLS.get(role, {}).get(skill, 0), reverse=True)[:2]),
                                   request.company, request.location,
                                   request.job_type or level, 'job opening careers requirements']))[:400]
            for role in (roles or [''])]


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
    queries = search_queries(request)
    automatic = not request.target_role
    jobs, warnings, results_by_url = [], [], {}

    def search(query):
        try:
            return search_web(query, 10, time_range='month', job_search=True), None
        except ServiceError as exc:
            return [], str(exc)

    with ThreadPoolExecutor(max_workers=3) as pool:
        for results, error in pool.map(search, queries):
            if error:
                warnings.append(error)
            for result in results:
                url = result.get('url', '')
                if url and (url not in results_by_url or result.get('raw_content')):
                    results_by_url[url] = result
    if not results_by_url and warnings:
        raise ServiceError(warnings[0])

    def read_job(url):
        indexed = job_from_index(results_by_url[url])
        if indexed:
            return [indexed], None
        if urlsplit(url).hostname in ('www.linkedin.com', 'linkedin.com'):
            return [], f'{url}: No substantive indexed description available for scoring.'
        try:
            soup, final_url = fetch_page(url)
            schemas = list(structured_items(soup, 'JobPosting'))
            found = [job_from_schema(item, final_url) for item in schemas] if schemas else [job_from_page(soup, final_url)]
            return [job for job in found if job], None
        except ServiceError as exc:
            return [], f'{url}: {exc}'

    today = datetime.now(timezone.utc).date()
    indexed_urls = []
    for url, result in results_by_url.items():
        job = job_from_index(result)
        if not job or (request.company and request.company.casefold() not in job.company.casefold()):
            continue
        posted = date_value(job.posted_at)
        if not posted or (posted <= today and (not automatic or posted >= today - timedelta(days=30))):
            indexed_urls.append(url)
    # Enough complete indexed descriptions: don't wait on unrelated blocked sources.
    urls = indexed_urls if len(indexed_urls) >= request.limit else list(results_by_url)[:24]
    with ThreadPoolExecutor(max_workers=5) as pool:
        for found, error in pool.map(read_job, urls):
            if error:
                warnings.append(error)
            for job in found:
                posted = date_value(job.posted_at)
                if posted and (posted > today or (automatic and posted < today - timedelta(days=30))):
                    continue
                if not request.company or request.company.casefold() in job.company.casefold():
                    jobs.append(job)
    if not jobs:
        warnings.append('No readable, structured job listings were found. Supply a job URL or description directly.')
    unique = {(job.job_url, job.company, job.role): job for job in jobs}
    return list(unique.values()), list(dict.fromkeys(warnings))
