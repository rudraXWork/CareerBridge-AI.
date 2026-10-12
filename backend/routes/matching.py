from fastapi import APIRouter

from backend.models import MatchRequest
from backend.nlp.job_parser import parse_job
from backend.nlp.matcher import match_resume
from backend.services.job_search import resolve_job
from backend.storage import save

router = APIRouter(tags=['Matching'])


@router.post('/match')
def match(data: MatchRequest):
    job = parse_job(resolve_job(data.job))
    result = match_resume(data.candidate, job)
    return {'id': save('match', result.model_dump()), 'job': job, 'match': result}
