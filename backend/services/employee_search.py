import re
from urllib.parse import urlsplit

from backend.config import CONTACT_WEIGHTS
from backend.models import Contact
from backend.services.company import company_aliases, company_name
from backend.services.web import ServiceError, fetch_page, search_web, structured_items

DEPARTMENTS = {
    'data': ['data', 'analytics', 'business intelligence', 'machine learning', 'artificial intelligence', 'ai'],
    'engineering': ['software', 'developer', 'engineering', 'backend', 'frontend', 'technical', 'technology', 'consulting', 'architect'],
    'design': ['design', 'ux', 'ui'],
    'finance': ['finance', 'accounting'],
    'marketing': ['marketing', 'content', 'growth'],
}


def department_for(role):
    for department, words in DEPARTMENTS.items():
        if any(re.search(r'\b' + re.escape(word) + r'\b', role, re.I) for word in words):
            return department
    return ''


def ideal_contacts(target_role):
    department = department_for(target_role)
    label = {'data': 'Data / Analytics', 'engineering': 'Engineering', 'design': 'Design',
             'finance': 'Finance', 'marketing': 'Marketing'}.get(department, target_role)
    return [f'{label} Hiring Manager', f'{label} Manager', 'Technical Recruiter',
            'Talent Acquisition Specialist', f'{label} Team Lead', f'Senior {target_role}']


def rank_contact(contact, target_role):
    target = department_for(target_role)
    actual = department_for(contact.role + ' ' + contact.department)
    lower = contact.role.lower()
    recruiter = bool(re.search(r'recruit|talent acquisition|human resources|people officer|\bhr\b|\bta\b', lower))
    manager = bool(re.search(r'manager|head|director|hiring', lower))
    lead = bool(re.search(r'lead|senior|staff|principal', lower))
    words = set(re.findall(r'\w+', target_role.lower())) - {'senior', 'junior', 'intern', 'of'}
    overlap = len(words & set(re.findall(r'\w+', lower))) / max(len(words), 1)
    components = {'role': max(overlap, 0.75 if target and actual == target else (0.5 if recruiter else 0)),
                  'department': 1 if target and actual == target else (0.7 if recruiter else 0),
                  'hiring': 1 if recruiter or ('hiring' in lower) else (0.9 if manager else (0.4 if lead else 0.1)),
                  'seniority': 1 if manager else (0.8 if lead or recruiter else 0.3)}
    score = sum(components[key] * weight for key, weight in CONTACT_WEIGHTS.items())
    return contact.model_copy(update={'relevance_score': round(score * 100, 2),
                                      'relevance_components': {k: round(v * 100, 2) for k, v in components.items()}})


def contacts_from_page(soup, company, url):
    contacts = []
    for item in structured_items(soup, 'Person'):
        org = item.get('worksFor') or item.get('affiliation') or {}
        orgs = org if isinstance(org, list) else [org]
        names = [value.get('name', '') if isinstance(value, dict) else str(value) for value in orgs]
        if not any(company_name(company) == company_name(name) for name in names):
            continue
        name, role = item.get('name', ''), item.get('jobTitle', '')
        if name and isinstance(role, str) and role:
            email = item.get('email', '')
            email = email.removeprefix('mailto:') if isinstance(email, str) else ''
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                email = ''
            contacts.append(Contact(name=name, role=role, company=company, department=department_for(role),
                                    profile_url=url, source='Public Person metadata',
                                    evidence=f'{name} — {role} — {company}',
                                    email=email, email_status='Public' if email else 'Unknown',
                                    email_source=url if email else '',
                                    warnings=['Public information may be outdated; confirm current employment.']))
    return contacts


def person_name(name):
    words = name.split()
    return (2 <= len(words) <= 5 and all(len(word.strip('.')) > 1 for word in (words[0], words[-1]))
            and bool(re.fullmatch(r'[A-Za-zÀ-ž .\x27-]+', name)))


def current_role(role):
    return (not re.search(r'\bformer\b|\bprevious\b|\bex-|\bpast\b', role, re.I)
            and bool(re.search(r'manager|engineer|scientist|analyst|developer|recruit|talent|lead|director|head|specialist|consultant|architect|officer', role, re.I)))


def attributed_role(text, company):
    aliases = '|'.join(re.escape(name) for name in company_aliases(company))
    match = re.fullmatch(r'(.+?)\s+(?:at|@)\s+(' + aliases + r')[.!]?', text.strip(), re.I)
    if match and current_role(match[1]):
        return match[1].strip()
    return ''


def contact_from_title(result, company):
    title = result.get('title', '')
    parts = re.split(r'\s+[|–—-]\s+', title)
    if len(parts) < 2 or not person_name(parts[0]):
        return None
    role = attributed_role(parts[1], company)
    if not role and len(parts) >= 3 and company_name(parts[2]) == company_name(company):
        role = parts[1] if current_role(parts[1]) else ''
    if not role:
        return None
    return Contact(name=parts[0], role=role, company=company, department=department_for(role),
                   profile_url=result.get('url', ''), source='Public search title', evidence=title,
                   warnings=['Search title is a discovery lead. Confirm current employment on the source page.'])


def contact_from_snippet(result, company):
    lines = [line.strip() for line in result.get('content', '').splitlines() if line.strip()]
    title_name = re.split(r'\s+[|–—-]\s+', result.get('title', ''))[0].strip()
    name = next((line.lstrip('# ').strip() for line in lines if line.startswith('# ') and person_name(line.lstrip('# ').strip())), title_name)
    if not person_name(name) or (person_name(title_name) and name.casefold() != title_name.casefold()):
        return None
    content = result.get('content', '')
    current = re.findall(r'(?:^|\n|\[\.\.\.\]\s*)Current role:\s*([^\n]+)', content, re.I)
    headlines = re.findall(r'(?:^|\n|\[\.\.\.\]\s*)Headline:\s*([^\n]+)', content, re.I)
    # The first experience entry can disprove an old headline.
    experience = re.search(r'## Experience\s*\n-\s+([^\n]+)', content, re.I)
    evidence = ''
    role = ''
    if experience:
        entry = experience[1].split(' [...]')[0]
        ongoing = re.fullmatch(r'(.+?)\s+\([^()]*\bto\s+present\)', entry, re.I)
        if ongoing:
            role = attributed_role(ongoing[1], company)
            if not role:
                return None
            evidence = entry
    if not role:
        for line in current or headlines:
            role = attributed_role(line.split(' [...]')[0], company)
            if role:
                evidence = line
                break
    if role:
        return Contact(name=name, role=role, company=company, department=department_for(role),
                       profile_url=result.get('url', ''), source='Public search snippet',
                       evidence=f'{name} — {evidence}',
                       warnings=['Search snippet is a discovery lead. Confirm current employment on the source page.'])
    return None


def discover_contacts(company, target_role, limit):
    types = ideal_contacts(target_role)
    query_company = company_aliases(company)[0]
    queries = [f'site:linkedin.com/in "{query_company}" {target_role} manager architect engineer',
               f'site:linkedin.com/in "{query_company}" recruiter talent acquisition human resources']
    results, warnings, seen_urls = [], [], set()
    for query in queries:
        try:
            found = search_web(query, 6)
        except ServiceError as exc:
            warnings.append(str(exc))
            continue
        for result in found:
            if result.get('url') and result['url'] not in seen_urls:
                results.append(result)
                seen_urls.add(result['url'])
    if not results and len(warnings) == len(queries):
        raise ServiceError(warnings[0])
    contacts = []
    for result in results:
        # A snippet showing a new employer must not be overridden by a stale title.
        content = result.get('content', '')
        contact = contact_from_snippet(result, company)
        if not contact and not re.search(r'Current role:|## Experience', content, re.I):
            contact = contact_from_title(result, company)
        if contact:
            contacts.append(contact)
        # Search evidence remains useful when the profile page blocks automated reading.
        host = urlsplit(result['url']).hostname or ''
        if host == 'linkedin.com' or host.endswith('.linkedin.com'):
            continue
        try:
            soup, url = fetch_page(result['url'])
            contacts.extend(contacts_from_page(soup, company, url))
        except (ServiceError, KeyError) as exc:
            warnings.append(f'Could not read employee source: {exc}')
    unique = {contact.name.casefold(): contact for contact in contacts}
    ranked = sorted((rank_contact(contact, target_role) for contact in unique.values()),
                    key=lambda c: c.relevance_score, reverse=True)
    if not ranked:
        warnings.append('The search could not confirm employees at this company. Try a broader area of interest or supply a person you know.')
    return ranked[:limit], types, list(dict.fromkeys(warnings))
