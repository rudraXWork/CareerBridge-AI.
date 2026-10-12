import os

from backend.config import EMBEDDING_MODEL, MODEL_PATH, ROOT

os.environ.setdefault('HF_HOME', str(ROOT / '.cache' / 'huggingface'))

if __name__ == '__main__':
    from spacy.cli import download
    from sentence_transformers import SentenceTransformer

    download('en_core_web_sm')
    model = SentenceTransformer(EMBEDDING_MODEL)
    model.save(str(MODEL_PATH))
    print('spaCy and MiniLM are ready. Local inference does not need the network.')
