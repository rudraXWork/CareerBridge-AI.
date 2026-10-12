import json
import re
from functools import lru_cache

from backend.config import ROOT


@lru_cache(maxsize=1)
def skill_data():
    path = ROOT / 'backend' / 'data'
    skills = json.loads((path / 'skills.json').read_text())
    aliases = json.loads((path / 'skill_aliases.json').read_text())
    lookup = {s.casefold(): s for s in skills}
    lookup.update({s.casefold(): value for s, value in aliases.items()})
    return lookup


def normalize_skills(skills):
    lookup = skill_data()
    return sorted({lookup.get(s.strip().casefold(), s.strip()) for s in skills if s.strip()})


def extract_skills(text):
    found = {}
    # Word boundaries alone do not work for C++, C# and .NET.
    for alias, skill in skill_data().items():
        flags = 0 if alias in ('r', 'go') else re.IGNORECASE
        word = skill if alias in ('r', 'go') else alias
        pattern = r'(?<![\w.+#])' + re.escape(word) + r'(?![\w+#])'
        match = re.search(pattern, text, flags)
        if match:
            found[skill] = match.group()
    return sorted(found.values(), key=str.casefold), sorted(found)


ROLE_SKILLS = {
    'Data Analyst': {'SQL': 3, 'Python': 2, 'Power BI': 3, 'Tableau': 2, 'Excel': 2, 'Data Analysis': 2},
    'Data Scientist': {'Python': 3, 'Machine Learning': 3, 'Pandas': 2, 'Scikit-learn': 2, 'Statistics': 2},
    'ML Engineer': {'Python': 3, 'Machine Learning': 3, 'PyTorch': 2, 'Docker': 2, 'Deep Learning': 2},
    'Backend Developer': {'Java': 2, 'Spring': 3, 'Python': 2, 'Node.js': 3, 'SQL': 2, 'REST API': 2},
    'Frontend Developer': {'JavaScript': 3, 'React': 3, 'HTML': 2, 'CSS': 2, 'TypeScript': 2},
    'Data Engineer': {'SQL': 3, 'Python': 2, 'ETL': 3, 'Spark': 3, 'Airflow': 3},
}


def suggest_roles(skills):
    roles = []
    for role, weights in ROLE_SKILLS.items():
        hits = set(skills) & weights.keys()
        if len(hits) >= 2:
            score = sum(weights[s] for s in hits) / sum(weights.values())
            roles.append((role, score))
    return [role for role, score in sorted(roles, key=lambda r: r[1], reverse=True)[:3]]
