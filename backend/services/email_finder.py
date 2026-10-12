import re

import dns.resolver

from backend.config import api_key
from backend.services.company import company_aliases, company_name, domain_from_web, known_domain
from backend.services.web import ServiceError, request_json

INVALID = {'invalid', 'undeliverable', 'disposable'}


def resolve_company_domain(company):
    domain = known_domain(company)
    if domain:
        return domain, 'Company website: https://www.hpe.com'
    key = api_key('HUNTER_API_KEY')
    notes = []
    if key:
        try:
            data = request_json('GET', 'https://api.hunter.io/v2/domain-finder', 'Hunter domain finder',
                                params={'company': company_aliases(company)[0], 'perfect_match': 'true',
                                        'limit': 5, 'api_key': key}).get('data') or []
            matches = {row.get('domain', '') for row in data
                       if company_name(row.get('company_name', '')) == company_name(company)} - {''}
            if len(matches) == 1:
                return matches.pop(), 'Hunter company domain lookup'
        except ServiceError as exc:
            notes.append(str(exc))
    try:
        domain, source = domain_from_web(company)
        if domain:
            return domain, source
    except ServiceError as exc:
        notes.append(str(exc))
    return '', 'Automatic search could not confirm this company’s email domain. Try again or use a more specific company name. ' + ' '.join(notes)


def email_checks(email, domain=''):
    valid = bool(re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', email))
    checks = {'syntax': valid, 'domain_exists': None, 'mx_records': None}
    if not valid:
        return checks
    host = email.rsplit('@', 1)[1].lower()
    checks['company_domain_match'] = host == domain.lower() if domain else None
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 3
    try:
        records = resolver.resolve(host, 'MX')
        checks['domain_exists'] = True
        checks['mx_records'] = any(str(row.exchange) != '.' for row in records)
    except dns.resolver.NXDOMAIN:
        checks['domain_exists'] = False
        checks['mx_records'] = False
    except dns.resolver.NoAnswer:
        checks['domain_exists'] = True
        checks['mx_records'] = False
    except dns.exception.DNSException:
        pass
    return checks


def pattern_emails(name, domain, pattern=''):
    words = re.findall(r'[a-z]+', name.lower())
    if len(words) < 2:
        return []
    first, last = words[0], words[-1]
    guesses = [f'{first}.{last}@{domain}', f'{first}@{domain}', f'{first[0]}{last}@{domain}']
    if pattern and re.fullmatch(r'(?:\{(?:first|last|f|l)\}|[._-])+', pattern):
        for token, value in [('first', first), ('last', last), ('f', first[0]), ('l', last[0])]:
            pattern = pattern.replace('{' + token + '}', value)
        guesses.insert(0, f'{pattern}@{domain}')
    return list(dict.fromkeys(guesses))


def company_pattern(domain):
    key = api_key('HUNTER_API_KEY')
    if not key:
        return ''
    data = request_json('GET', 'https://api.hunter.io/v2/domain-search', 'Hunter domain pattern',
                        params={'domain': domain, 'limit': 1, 'type': 'personal', 'api_key': key}).get('data') or {}
    if (data.get('domain') or '').lower() != domain:
        return ''
    return data.get('pattern') or ''


def hunter_lookup(contact, domain):
    key = api_key('HUNTER_API_KEY')
    if not key:
        return None
    return request_json('GET', 'https://api.hunter.io/v2/email-finder', 'Hunter',
                        params={'domain': domain, 'full_name': contact.name, 'api_key': key}).get('data')


def apollo_lookup(contact, domain):
    key = api_key('APOLLO_API_KEY')
    if not key:
        return None
    data = request_json('POST', 'https://api.apollo.io/api/v1/people/match', 'Apollo',
                        headers={'X-Api-Key': key},
                        json={'name': contact.name, 'domain': domain,
                              'reveal_personal_emails': False, 'reveal_phone_number': False})
    person = data.get('person') or {}
    # A name match at another company should not silently become our contact.
    if person.get('email') and person['email'].rsplit('@', 1)[-1].lower() == domain:
        return person
    return None


def provider_status(status, sources=False):
    if status in ('valid', 'verified'):
        return 'Verified'
    if status in ('accept_all', 'catch_all'):
        return 'Likely'
    if status in ('invalid', 'undeliverable', 'disposable'):
        return 'Unknown'
    return 'Public' if sources else 'Unknown'


def verify_email(email):
    key = api_key('HUNTER_API_KEY')
    if not key:
        return {}
    return request_json('GET', 'https://api.hunter.io/v2/email-verifier', 'Hunter verifier',
                        params={'email': email, 'api_key': key}).get('data') or {}


def find_email(contact, domain, allow_patterns=False):
    contact = contact.model_copy(deep=True)
    if contact.email:
        # Known emails do not need a finder call.
        public = contact.source == 'Public Person metadata'
        contact.email_status = 'Public' if public else 'Unknown'
        contact.email_source = contact.profile_url if public else 'User supplied'
        contact.confidence = None
        contact.email_checks = email_checks(contact.email, domain)
        contact.warnings.append('Known email has basic checks only; mailbox deliverability is unverified.')
        return contact
    domain = domain.lower().strip()
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}', domain):
        contact.warnings.append('Automatic company-domain lookup did not return a usable domain. Try finding email again.')
        return contact
    for provider, lookup in [('Hunter', hunter_lookup), ('Apollo', apollo_lookup)]:
        try:
            data = lookup(contact, domain)
        except ServiceError as exc:
            contact.warnings.append(str(exc))
            continue
        if not data or not data.get('email'):
            continue
        email = data['email']
        if email.rsplit('@', 1)[-1].lower() != domain:
            contact.warnings.append(f'{provider} returned another domain; review the company domain before using it.')
            continue
        verification = data.get('verification') or {}
        status = verification.get('status') if provider == 'Hunter' else data.get('email_status')
        if status in INVALID:
            contact.warnings.append(f'{provider} returned an undeliverable address; it was not selected.')
            continue
        if api_key('HUNTER_API_KEY') and status not in ('valid', 'verified', 'accept_all', 'catch_all'):
            try:
                checked = verify_email(email)
                status = checked.get('status')
                verification = checked
            except ServiceError as exc:
                contact.warnings.append(str(exc))
        if status in INVALID:
            contact.warnings.append(f'{provider} address failed verification; it was not selected.')
            continue
        checks = email_checks(email, domain)
        if not checks['syntax'] or checks.get('mx_records') is False:
            contact.warnings.append(f'{provider} address failed basic email checks; it was not selected.')
            continue
        contact.email = email
        contact.email_source = provider
        contact.confidence = data.get('score')
        contact.email_status = provider_status(status, bool(data.get('sources')))
        contact.email_checks = {**checks, 'provider_status': status, 'provider_verification': verification,
                                'sources': data.get('sources', [])}
        if contact.email_status == 'Likely':
            contact.warnings.append('The company uses a catch-all mail server. This individual mailbox is not confirmed.')
        elif contact.email_status != 'Verified':
            contact.warnings.append('This address has not been confirmed as deliverable by an email verifier.')
        return contact
    if not api_key('HUNTER_API_KEY') and not api_key('APOLLO_API_KEY'):
        contact.warnings.append('Hunter and Apollo keys are missing; no provider lookup was performed.')
    if allow_patterns:
        pattern = ''
        try:
            pattern = company_pattern(domain)
        except ServiceError as exc:
            contact.warnings.append(str(exc))
        contact.inferred_emails = pattern_emails(contact.name, domain, pattern)
        checked_patterns = {}
        for email in contact.inferred_emails:
            checks = email_checks(email, domain)
            if not checks['syntax'] or checks.get('mx_records') is False:
                checked_patterns[email] = 'invalid'
                continue
            try:
                checked = verify_email(email)
            except ServiceError as exc:
                contact.warnings.append(str(exc))
                checked = {}
            status = checked.get('status', 'unverified')
            checked_patterns[email] = status
            if status in INVALID:
                continue
            contact.email = email
            contact.email_source = 'Name and domain pattern' + (' + Hunter verification' if checked else '')
            contact.email_status = provider_status(status) if status in ('valid', 'verified', 'accept_all', 'catch_all') else 'Inferred'
            contact.email_checks = {**checks, 'provider_status': status, 'provider_verification': checked}
            # Catch-all and unknown results cannot distinguish additional guesses.
            break
        contact.email_checks['pattern_checks'] = checked_patterns
        if pattern:
            contact.email_checks['company_pattern'] = pattern
            contact.email_checks['pattern_source'] = 'Hunter Domain Search'
        contact.warnings.append('Name/domain patterns are guesses. Only a valid provider check confirms deliverability; catch-all and MX checks do not confirm this mailbox or its owner.')
    return contact
