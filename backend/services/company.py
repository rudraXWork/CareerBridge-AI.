import re
from urllib.parse import urlsplit

from backend.services.web import search_web


def company_name(name):
    name = re.sub(r'\s+', ' ', name.strip()).casefold()
    # HPE and HP Inc. are separate companies.
    if name in ('hpe', 'hewlett packard enterprise', 'hewlett-packard enterprise'):
        return 'hewlett packard enterprise'
    return name


def company_aliases(name):
    if company_name(name) == 'hewlett packard enterprise':
        return ['Hewlett Packard Enterprise', 'Hewlett-Packard Enterprise', 'HPE']
    return [name.strip()]


def known_domain(name):
    if company_name(name) == 'hewlett packard enterprise':
        return 'hpe.com'
    return ''


def domain_from_web(company):
    aliases = company_aliases(company)
    words = re.findall(r'[a-z0-9]+', aliases[0].lower())
    words = [word for word in words if word not in {'the', 'and', 'of', 'inc', 'ltd', 'llc', 'limited', 'company', 'corporation'}]
    if not words:
        return '', ''
    brands = {words[0], ''.join(words), '-'.join(words)}
    if len(words) > 1:
        brands.add(''.join(word[0] for word in words))
    brand = '|'.join(re.escape(word) for word in brands)
    # Match the company host, including common country domains, not a job board.
    host_pattern = r'(?:^|\.)((?:' + brand + r')\.(?:(?:co|com|org|net|ac)\.[a-z]{2}|[a-z]{2,63}))$'
    candidates = {}
    for row in search_web(f'"{aliases[0]}" official website contact email', 5):
        parts = urlsplit(row.get('url', ''))
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            continue
        text = row.get('title', '') + ' ' + row.get('content', '')
        if not any(re.search(r'\b' + re.escape(alias) + r'\b', text, re.I) for alias in aliases):
            continue
        match = re.search(host_pattern, parts.hostname.lower())
        if not match:
            continue
        domain = match[1]
        emails = re.findall(r'[\w.+-]+@([a-z0-9.-]+\.[a-z]{2,63})', row.get('content', '').lower())
        count = sum(email.rstrip('.') == domain for email in emails)
        score = 1 + 3 * count
        if domain not in candidates or score > candidates[domain][0]:
            candidates[domain] = (score, row['url'])
    if not candidates:
        return '', ''
    ranked = sorted(candidates, key=lambda domain: candidates[domain][0], reverse=True)
    if len(ranked) > 1 and candidates[ranked[0]][0] == candidates[ranked[1]][0]:
        return '', ''
    domain = ranked[0]
    return domain, 'Public company source: ' + candidates[domain][1]
