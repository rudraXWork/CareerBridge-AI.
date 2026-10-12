import json

from backend.config import ROOT
from backend.models import JobInput
from backend.nlp.job_parser import parse_job
from backend.nlp.matcher import match_resume
from backend.nlp.resume_parser import parse_resume
from backend.nlp.skills import extract_skills


def evaluate():
    labels = json.loads((ROOT / 'examples' / 'skill_labels.json').read_text())
    tp = fp = fn = 0
    for case in labels:
        predicted = set(extract_skills(case['text'])[1])
        actual = set(case['skills'])
        tp += len(predicted & actual)
        fp += len(predicted - actual)
        fn += len(actual - predicted)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    candidate = parse_resume((ROOT / 'examples' / 'resume.txt').read_text())
    jobs = json.loads((ROOT / 'examples' / 'jobs.json').read_text())
    rows = []
    for label, item in zip(['High match', 'Medium match', 'Low match'], jobs):
        job = parse_job(JobInput(**item))
        match = match_resume(candidate, job)
        rows.append({'expected': label, 'role': job.role, 'result': match.model_dump()})
    scores = [row['result']['score'] for row in rows]
    result = {
        'note': 'Small synthetic classroom examples that informed development. Not a blind benchmark or hiring prediction.',
        'skill_extraction': {'examples': len(labels), 'tp': tp, 'fp': fp, 'fn': fn,
                             'precision': round(precision, 4), 'recall': round(recall, 4),
                             'f1': round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0},
        'matches': rows,
        'expected_order_observed': scores[0] > scores[1] > scores[2] if all(s is not None for s in scores) else None,
        'live_providers_verified': False,
    }
    (ROOT / 'evaluation' / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'skill_extraction': result['skill_extraction'],
                      'scores': scores, 'expected_order_observed': result['expected_order_observed']}, indent=2))
    return result


if __name__ == '__main__':
    evaluate()
