import json

import pytest

from backend import config
from backend.nlp.resume_parser import parse_resume


@pytest.fixture(autouse=True)
def isolate_database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'test.db')
    for name in ('LLM_API_KEY', 'GROQ_API_KEY', 'TAVILY_API_KEY', 'HUNTER_API_KEY', 'APOLLO_API_KEY'):
        monkeypatch.setenv(name, '')


@pytest.fixture
def candidate():
    return parse_resume((config.ROOT / 'examples' / 'resume.txt').read_text())


@pytest.fixture
def jobs():
    return json.loads((config.ROOT / 'examples' / 'jobs.json').read_text())
