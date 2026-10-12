import re

from sklearn.feature_extraction.text import TfidfVectorizer

from backend.models import JobInput, JobProfile
from backend.nlp.resume_parser import clean_text, load_nlp
from backend.nlp.skills import extract_skills


def parse_job(job: JobInput):
    text = clean_text(job.job_description)
    required, preferred, responsibilities = set(), set(), []
    experience, education, years = [], [], []
    mode = 'required'
    for line in text.splitlines():
        lower = line.lower()
        if re.search(r'preferred|nice.to.have|bonus|desirable', lower):
            mode = 'preferred'
        elif re.search(r'required|requirements|must.have|essential|minimum qualifications', lower):
            mode = 'required'
        elif re.search(r'responsibilities|what you.ll do|duties', lower):
            mode = 'responsibilities'
        elif lower.strip(' :•-') in ('education', 'education requirements', 'educational qualifications'):
            mode = 'education'
        for sent in load_nlp()(line).sents:
            value = sent.text.strip(' •-')
            local_mode = mode
            if re.search(r'preferred|nice.to.have|bonus|desirable', value, re.I):
                local_mode = 'preferred'
            elif re.search(r'required|must|essential', value, re.I):
                local_mode = 'required'
            is_education = bool(re.search(r'bachelor|master|degree|b\.?tech|b\.?sc|ph\.?d|diploma', value, re.I))
            skills = extract_skills(value)[1] if local_mode != 'education' and not is_education else []
            (preferred if local_mode == 'preferred' else required).update(skills)
            if local_mode == 'responsibilities' and len(value.split()) > 3:
                responsibilities.append(value)
            elif re.match(r'(you will|responsible for|build|develop|analy[sz]e|maintain|design)\b', value, re.I):
                responsibilities.append(value)
            if re.search(r'\d+\+?\s*(?:-\s*\d+\s*)?years?|no experience|entry.level|graduate', value, re.I):
                experience.append(value)
                if local_mode != 'preferred':
                    years.extend(re.findall(r'(\d+)\s*(?:\+|[-–]\s*\d+)?\s*years?\s+(?:of\s+)?(?:\w+\s+){0,3}experience', value, re.I))
            if is_education and local_mode != 'preferred':
                education.append(value)
    role_text = job.role.lower()
    if re.search(r'\b(senior|lead|staff|principal|manager|director)\b', role_text):
        seniority = 'Senior'
    elif re.search(r'\b(intern|graduate|entry|junior|associate)\b', role_text + ' ' + ' '.join(experience).lower()):
        seniority = 'Entry level'
    else:
        seniority = 'Unknown'
    keywords = []
    if text:
        try:
            vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), max_features=40)
            row = vectorizer.fit_transform([text]).toarray()[0]
            words = vectorizer.get_feature_names_out()
            keywords = [words[i] for i in row.argsort()[::-1][:12]]
        except ValueError:
            pass
    warnings = []
    if len(text.split()) < 30:
        warnings.append('A substantive job description is unavailable; no overall match score will be calculated.')
    return JobProfile(**{**job.model_dump(include=set(JobInput.model_fields)), 'job_description': text},
                      required_skills=sorted(required), preferred_skills=sorted(preferred - required),
                      responsibilities=responsibilities, experience_required='\n'.join(experience),
                      min_experience_years=max(map(float, years)) if years else None,
                      education_required='\n'.join(education), tools=sorted(required | preferred),
                      keywords=keywords, seniority=seniority, warnings=warnings)
