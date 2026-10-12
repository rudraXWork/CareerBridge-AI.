from fastapi import APIRouter, HTTPException

from backend.models import EmailRequest
from backend.nlp.job_parser import parse_job
from backend.nlp.matcher import match_resume
from backend.services.job_search import resolve_job
from backend.services.llm import build_context, generate_email
from backend.storage import save

router = APIRouter(prefix='/email', tags=['Email'])


@router.post('/generate')
def email(data: EmailRequest):
    if not data.job.company or not data.job.role:
        raise HTTPException(422, 'Supply the target company and role before generating an email.')
    job = parse_job(resolve_job(data.job))
    if data.employee.company and data.employee.company.casefold() != job.company.casefold():
        raise HTTPException(422, 'Employee and job companies must match.')
    # A company introduction does not require a vacancy or a match score.
    match = match_resume(data.candidate, job) if job.job_description.strip() else None
    context = build_context(data.candidate, job, match, data.employee, data.company_context, data.tone, data.purpose)
    draft = generate_email(context)
    record = {'email': draft.model_dump(), 'context': context}
    return {'id': save('email', record), 'email': draft, 'match': match,
            'note': 'Review factual claims, then copy and send manually.'}
