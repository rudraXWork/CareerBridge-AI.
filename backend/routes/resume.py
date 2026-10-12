from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from backend.config import MAX_UPLOAD
from backend.models import ResumeAnalysisRequest
from backend.nlp.resume_health import analyze_resume, inspect_document
from backend.nlp.resume_parser import extract_text, parse_resume
from backend.services.resume_insights import generate_resume_insights
from backend.services.resume_export import resume_pdf
from backend.storage import save

router = APIRouter(prefix='/resume', tags=['Resume'])


@router.post('/upload')
def upload_resume(file: UploadFile = File(...)):
    content = file.file.read(MAX_UPLOAD + 1)
    try:
        text = extract_text(content, file.filename or '')
        profile = parse_resume(text)
        profile.document = inspect_document(content, file.filename or '', text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    rid = save('candidate', profile.model_dump())
    return {'id': rid, 'profile': profile, 'text': text, 'health': analyze_resume(profile),
            'next_step': 'Review the profile. Send corrected normalized_skills and details to the next endpoint.'}


@router.post('/analyze')
def analyze(data: ResumeAnalysisRequest):
    return {'health': analyze_resume(data.candidate)}


@router.post('/insights')
def insights(data: ResumeAnalysisRequest):
    return {'insights': generate_resume_insights(data.candidate)}


@router.post('/download')
def download_resume(data: ResumeAnalysisRequest):
    return Response(resume_pdf(data.candidate), media_type='application/pdf',
                    headers={'Content-Disposition': 'attachment; filename="reviewed-resume.pdf"'})
