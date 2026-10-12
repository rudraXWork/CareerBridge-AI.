from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import MODEL_PATH, SPACY_MODEL, api_key
from backend.nlp.resume_parser import load_nlp
from backend.routes import contacts, email, jobs, matching, resume
from backend.services.web import ServiceError

app = FastAPI(title='CareerBridge AI', version='0.1.0',
              description='Local NLP and explainable matching, followed by personalized email drafting.')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
                   allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
for router in (resume.router, jobs.router, matching.router, contacts.router, email.router):
    app.include_router(router)


@app.exception_handler(ServiceError)
async def service_error(request: Request, exc: ServiceError):
    return JSONResponse(status_code=503, content={'detail': str(exc)})


@app.get('/health')
def health():
    return {'status': 'ok', 'spacy_model': SPACY_MODEL if 'ner' in load_nlp().pipe_names else 'blank English (rules only)',
            'embeddings_installed': MODEL_PATH.exists(),
            'providers_configured': {name: bool(api_key(name)) for name in
                                     ('LLM_API_KEY', 'GROQ_API_KEY', 'TAVILY_API_KEY', 'HUNTER_API_KEY', 'APOLLO_API_KEY')},
            'live_providers_verified': False}
