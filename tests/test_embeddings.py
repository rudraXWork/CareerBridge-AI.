import pytest

from backend.config import MODEL_PATH
from backend.models import JobInput
from backend.nlp.embeddings import similarities
from backend.nlp.job_parser import parse_job
from backend.nlp.matcher import match_resume

pytestmark = pytest.mark.skipif(not MODEL_PATH.exists(), reason='Run download_models.py to test real local MiniLM inference')


def test_actual_semantic_similarity():
    scores = similarities(['Python SQL Power BI sales dashboard analytics',
                           'Java Spring Kubernetes backend microservices'],
                          'Data analyst using Python SQL and Power BI for sales analytics')
    assert 0 <= scores[1] < scores[0] <= 1


def test_actual_match_order(candidate, jobs):
    scores = [match_resume(candidate, parse_job(JobInput(**job))).score for job in jobs]
    assert all(score is not None for score in scores)
    assert scores[0] > scores[1] > scores[2]
