import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

SPACY_MODEL = 'en_core_web_sm'
EMBEDDING_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
MODEL_PATH = ROOT / 'models' / 'all-MiniLM-L6-v2'
DB_PATH = ROOT / 'backend' / 'data' / 'app.db'
MAX_UPLOAD = 5 * 1024 * 1024
MAX_TEXT = 50_000
MATCH_WEIGHTS = {
    'skills': 0.40, 'semantic': 0.25, 'projects': 0.20,
    'experience': 0.10, 'education': 0.05,
}
CONTACT_WEIGHTS = {'role': 0.40, 'department': 0.30, 'hiring': 0.20, 'seniority': 0.10}


def api_key(name):
    value = os.getenv(name, '').strip()
    if value.lower().startswith(('your_', 'replace_', 'placeholder')):
        return ''
    return value
