import re

from backend.config import MATCH_WEIGHTS
from backend.models import CandidateProfile, JobProfile, MatchResult
from backend.nlp.embeddings import similarities
from backend.nlp.skills import extract_skills, normalize_skills


def education_score(candidate, required):
    if not required.strip():
        return None
    text = ' '.join(candidate.education).lower()
    degree_words = {
        1: r'diploma|associate',
        2: r'bachelor|b\.?\s*tech|b\.?\s*sc|b\.?\s*e\b|undergraduate',
        3: r'master|m\.?\s*tech|m\.?\s*sc|mba',
        4: r'ph\.?\s*d|doctorate',
    }
    needed = max((n for n, pattern in degree_words.items() if re.search(pattern, required, re.I)), default=0)
    actual = max((n for n, pattern in degree_words.items() if re.search(pattern, text)), default=0)
    if not needed:
        return None
    degree = 1 if actual >= needed else (0.5 if actual else 0)
    fields = ['computer science', 'information technology', 'statistics', 'mathematics', 'engineering', 'business']
    wanted = [field for field in fields if field in required.lower()]
    field_score = 1 if not wanted or any(field in text for field in wanted) else 0.5
    return degree * field_score


def experience_score(candidate, job):
    years = candidate.experience_years
    needed = job.min_experience_years
    if needed is not None and needed > 0:
        if years is not None:
            return min(years / needed, 1.0)
        return 0.25 if needed <= 1 and candidate.projects else 0.0
    if job.seniority == 'Entry level':
        return 1.0 if candidate.experience or candidate.projects else 0.5
    if job.seniority == 'Senior':
        return min((years or 0) / 5, 1.0)
    return None


def match_resume(candidate: CandidateProfile, job: JobProfile):
    if len(job.job_description.split()) < 30:
        return MatchResult(explanation='Provide a full job description to calculate a meaningful match.',
                           warnings=job.warnings)
    # The editable normalized list is the source of truth after profile review.
    skills = set(normalize_skills(candidate.normalized_skills))
    required, preferred = set(job.required_skills), set(job.preferred_skills)
    matched = skills & required
    missing = required - skills
    skill_score = len(matched) / len(required) if required else None
    if preferred:
        pref_score = len(skills & preferred) / len(preferred)
        skill_score = 0.85 * skill_score + 0.15 * pref_score if skill_score is not None else pref_score
    text = '\n'.join([candidate.summary, *candidate.projects, *candidate.experience, ' '.join(sorted(skills))])
    warnings, projects = [], []
    semantic, project_score = None, None
    try:
        scores = similarities([text, *candidate.projects], job.job_description)
        semantic = scores[0] if text.strip() else 0
        for project, score in zip(candidate.projects, scores[1:]):
            overlap = len(set(extract_skills(project)[1]) & (required | preferred)) / max(len(required | preferred), 1)
            projects.append({'text': project, 'score': round((0.5 * overlap + 0.5 * score) * 100, 2)})
        project_score = max((p['score'] / 100 for p in projects), default=0)
    except (OSError, ValueError) as exc:
        warnings.append(str(exc))
    exp_score = experience_score(candidate, job)
    edu_score = education_score(candidate, job.education_required)
    components = {'skills': skill_score, 'semantic': semantic, 'projects': project_score,
                  'experience': exp_score, 'education': edu_score}
    coverage = sum(MATCH_WEIGHTS[key] for key, value in components.items() if value is not None)
    weights = {key: value / coverage for key, value in MATCH_WEIGHTS.items()
               if components[key] is not None} if coverage else {}
    # No overall percentage without the semantic model; partial skills are still useful.
    score = sum(components[key] * weight for key, weight in weights.items()) * 100 if semantic is not None else None
    if coverage < 1:
        warnings.append('Unavailable components are excluded; weights are redistributed and evidence coverage is shown.')
    if semantic is None:
        warnings.append('Overall score is unavailable until MiniLM is installed. Skill comparisons are still shown.')
    gaps = [f'Preferred: {s}' for s in sorted(preferred - skills)]
    if job.min_experience_years and exp_score is not None and exp_score < 1:
        actual = f'{candidate.experience_years:g} years stated' if candidate.experience_years is not None else 'years not stated'
        gaps.append(f'{job.min_experience_years:g} years required; {actual}')
    elif job.seniority == 'Senior' and exp_score is not None and exp_score < 1:
        gaps.append('Senior role; sufficient professional experience is not demonstrated.')
    if edu_score is not None and edu_score < 1:
        gaps.append('Education requirement is not fully supported by the profile.')
    explanation = f'Matched {len(matched)} of {len(required)} required skills.'
    if matched:
        explanation += ' Strengths: ' + ', '.join(sorted(matched)) + '.'
    if missing or gaps:
        explanation += ' Gaps: ' + ', '.join(sorted(missing) + gaps) + '.'
    return MatchResult(score=round(score, 2) if score is not None else None,
                       components={key: round(value * 100, 2) if value is not None else None
                                   for key, value in components.items()},
                       weights_used=weights, evidence_coverage=round(coverage * 100, 2),
                       strong_matches=sorted(skills & (required | preferred)), missing_skills=sorted(missing),
                       gaps=gaps, relevant_projects=sorted(projects, key=lambda p: p['score'], reverse=True),
                       explanation=explanation, warnings=warnings)
