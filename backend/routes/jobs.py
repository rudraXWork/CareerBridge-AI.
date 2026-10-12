from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.config import MAX_UPLOAD
from backend.models import JobInput, JobSearchRequest
from backend.nlp.job_parser import parse_job
from backend.nlp.matcher import match_resume
from backend.nlp.resume_parser import clean_text, extract_text
from backend.services.job_search import discover_jobs, resolve_job
from backend.storage import save

router = APIRouter(prefix='/jobs', tags=['Jobs'])


@router.post('/upload')
def upload_description(file: UploadFile = File(...)):
    filename = file.filename or ''
    if not filename.lower().endswith(('.pdf', '.docx')):
        raise HTTPException(422, 'Choose a PDF or Word (.docx) job description.')
    content = file.file.read(MAX_UPLOAD + 1)
    if not content or len(content) > MAX_UPLOAD:
        raise HTTPException(422, 'Choose a non-empty job description file up to 5 MB.')
    try:
        text = clean_text(extract_text(content, filename))
    except ValueError as exc:
        raise HTTPException(422, str(exc).replace('resume', 'job description').replace('Resume', 'Job description')) from exc
    return {'text': text}


@router.post('/analyze')
def analyze_job(data: JobInput):
    job = parse_job(resolve_job(data))
    return {'id': save('job', job.model_dump()), 'job': job}


@router.post('/search')
def search_jobs(data: JobSearchRequest):
    jobs, warnings = discover_jobs(data)
    opportunities = []
    for item in jobs:
        job = parse_job(item)
        match = match_resume(data.candidate, job)
        opportunities.append({'id': save('job', job.model_dump()), 'job': job, 'match': match})
    opportunities.sort(key=lambda item: item['match'].score if item['match'].score is not None else -1,
                       reverse=True)
    return {'opportunities': opportunities, 'warnings': warnings,
            'note': 'Scores are local heuristics, not hiring probabilities. Confirm listings are still open.'}
