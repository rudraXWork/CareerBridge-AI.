from fastapi import APIRouter, HTTPException

from backend.models import ContactRequest
from backend.services.company import company_name
from backend.services.email_finder import find_email, resolve_company_domain
from backend.services.employee_search import discover_contacts, ideal_contacts, rank_contact
from backend.storage import save

router = APIRouter(prefix='/contacts', tags=['Contacts'])


@router.post('/find')
def find_contacts(data: ContactRequest):
    warnings = []
    if data.person:
        if data.person.company and company_name(data.person.company) != company_name(data.company):
            raise HTTPException(422, 'The supplied person and target company must match.')
        person = data.person.model_copy(update={'company': data.company, 'source': 'User supplied',
                                              'email_status': 'Unknown',
                                              'email_source': 'User supplied' if data.person.email else '',
                                              'confidence': None, 'warnings': [], 'email_checks': {}, 'inferred_emails': []})
        if person.evidence and person.profile_url:
            person.warnings.append('Search evidence is a discovery lead. Confirm current employment on the source page.')
        contacts = [rank_contact(person, data.target_role)]
        types = ideal_contacts(data.target_role)
    else:
        contacts, types, warnings = discover_contacts(data.company, data.target_role, data.limit)
    domain, domain_source = data.company_domain.strip().lower(), ''
    if data.find_email:
        if contacts and not domain and any(not contact.email for contact in contacts):
            domain, domain_source = resolve_company_domain(data.company)
            if not domain:
                warnings.append(domain_source)
        contacts = [find_email(contact, domain, data.allow_patterns) if domain or contact.email else contact
                    for contact in contacts]
    for contact in contacts:
        contact.warnings = list(dict.fromkeys(contact.warnings))
        if data.find_email and domain:
            contact.email_checks['company_domain'] = domain
            if domain_source:
                contact.email_checks['domain_source'] = domain_source
        save('contact', contact.model_dump())
    return {'contacts': contacts, 'ideal_contact_types': types, 'warnings': warnings,
            'company_domain': domain, 'domain_source': domain_source,
            'note': 'Contact relevance measures role suitability, not likelihood of a reply.'}
