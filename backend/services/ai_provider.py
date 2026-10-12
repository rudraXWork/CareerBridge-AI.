import os

from backend.config import api_key
from backend.services.web import ServiceError


def with_groq_fallback(generate, context):
    try:
        return generate(context, api_key('LLM_API_KEY'),
                        os.getenv('LLM_BASE_URL', '').strip().rstrip('/'),
                        os.getenv('LLM_MODEL', '').strip())
    except ServiceError as exc:
        key = api_key('GROQ_API_KEY')
        if not key:
            raise
        primary_error = str(exc)
    try:
        return generate(context, key, 'https://api.groq.com/openai/v1',
                        'openai/gpt-oss-120b')
    except ServiceError as exc:
        raise ServiceError(f'Primary AI failed: {primary_error} Groq fallback failed: {exc}') from exc
