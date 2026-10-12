from io import BytesIO

import pymupdf
import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.main import app


@pytest.mark.parametrize('ext', ['pdf', 'docx'])
def test_job_document_text_can_be_reviewed_and_matched(ext, candidate, monkeypatch):
    text = ('Data Analyst\nRequired skills: Python, SQL and Power BI.\n'
            'Analyze sales data and build dashboards for business teams.\n'
            'Work with stakeholders to explain trends, maintain reports, and improve data quality.')
    if ext == 'pdf':
        doc = pymupdf.open()
        doc.new_page().insert_text((40, 60), text)
        content = doc.tobytes()
        doc.close()
    else:
        doc = Document()
        for line in text.splitlines():
            doc.add_paragraph(line)
        buf = BytesIO()
        doc.save(buf)
        content = buf.getvalue()
    monkeypatch.setattr('backend.services.web.request_json', lambda *args, **kwargs: pytest.fail('Upload is local'))
    monkeypatch.setattr('backend.nlp.matcher.similarities', lambda texts, target: [0.8] * len(texts))
    client = TestClient(app)
    res = client.post('/jobs/upload', files={'file': (f'job.{ext.upper()}', content)})
    assert res.status_code == 200
    assert res.json()['text'] == text
    res = client.post('/match', json={'candidate': candidate.model_dump(), 'job': {
        'company': 'Example Company', 'role': 'Data Analyst',
        'job_description': res.json()['text'] + '\nExcel required.'}})
    assert res.status_code == 200
    assert 'Excel' in res.json()['job']['required_skills']
    assert res.json()['match']['score'] is not None


@pytest.mark.parametrize('filename,content', [
    ('job.txt', b'Python required'), ('job.doc', b'old Word format'),
    ('job.pdf', b''), ('job.pdf', b'not a PDF'), ('job.docx', b'not a Word document'),
])
def test_invalid_job_upload_returns_recoverable_error(filename, content):
    res = TestClient(app).post('/jobs/upload', files={'file': (filename, content)})
    assert res.status_code == 422
    assert res.json()['detail']
    assert 'resume' not in res.json()['detail'].lower()


def test_job_upload_size_limit(monkeypatch):
    monkeypatch.setattr('backend.routes.jobs.MAX_UPLOAD', 10)
    res = TestClient(app).post('/jobs/upload', files={'file': ('job.pdf', b'x' * 11)})
    assert res.status_code == 422
    assert 'job description' in res.json()['detail']


def test_scanned_job_pdf_explains_how_to_recover():
    doc = pymupdf.open()
    doc.new_page()
    content = doc.tobytes()
    doc.close()
    res = TestClient(app).post('/jobs/upload', files={'file': ('job.pdf', content)})
    assert res.status_code == 422
    assert 'OCR' in res.json()['detail']
