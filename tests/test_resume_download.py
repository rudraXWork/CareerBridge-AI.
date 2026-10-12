import unicodedata

import pymupdf
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import CandidateProfile


ORIGINAL = 'Built a Python dashboard to compare monthly sales from CSV files.'


def test_auto_apply_endpoint_is_removed():
    assert TestClient(app).post('/resume/apply-insight', json={}).status_code == 404


def test_pdf_paginates_without_losing_text_and_escapes_markup():
    profile = CandidateProfile(name='Alex <Example>', summary='Used Python & SQL.',
                               projects=['• ' + ORIGINAL] * 100,
                               sections={'achievements': 'Placed first in a classroom competition.'})
    res = TestClient(app).post('/resume/download', json={'candidate': profile.model_dump()})
    with pymupdf.open(stream=res.content, filetype='pdf') as doc:
        assert len(doc) > 1
        text = unicodedata.normalize('NFKC', ' '.join(' '.join(page.get_text().split()) for page in doc))
    assert text.count(ORIGINAL) == 100
    assert 'Alex <Example>' in text and 'Python & SQL' in text
    assert 'Placed first in a classroom competition.' in text
