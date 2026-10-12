from functools import lru_cache

from sklearn.metrics.pairwise import cosine_similarity

from backend.config import MODEL_PATH


@lru_cache(maxsize=1)
def load_embeddings():
    if not MODEL_PATH.exists():
        raise OSError('MiniLM is missing. Run python download_models.py before semantic matching.')
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(str(MODEL_PATH), local_files_only=True)


def similarities(texts, target):
    if not texts or not target.strip():
        return []
    model = load_embeddings()
    vectors = model.encode(texts + [target], normalize_embeddings=True)
    scores = cosine_similarity(vectors[:-1], vectors[-1:]).ravel()
    return [max(0.0, min(1.0, float(score))) for score in scores]
