from html import escape
from io import BytesIO
import re

import pymupdf


def resume_pdf(candidate):
    html = f'<h1>{escape(candidate.name or "Resume")}</h1>'
    if candidate.email:
        html += f'<p class="contact">{escape(candidate.email)}</p>'
    sections = [('Summary', [candidate.summary] if candidate.summary else []),
                ('Education', candidate.education),
                ('Skills', [', '.join(candidate.normalized_skills)] if candidate.normalized_skills else []),
                ('Projects', candidate.projects), ('Experience', candidate.experience),
                ('Certifications', candidate.certifications)]
    used = {'header', 'summary', 'education', 'skills', 'projects', 'experience', 'certifications'}
    sections += [(key.replace('_', ' ').title(), value.splitlines())
                 for key, value in candidate.sections.items() if key not in used and value.strip()]
    for title, lines in sections:
        if not lines:
            continue
        html += f'<h2>{escape(title)}</h2>'
        text = [line.strip() for item in lines for line in item.splitlines() if line.strip()]
        for i, line in enumerate(text):
            if re.fullmatch(r'[•●▪*]', line):
                continue
            heading = (not re.match(r'^(?:[•●▪*]|[-–]\s+|\d+[.)]\s+)', line)
                       and ('|' in line or (not re.search(r'[.!?]$', line)
                       and i + 1 < len(text) and re.match(r'^[•●▪*]', text[i + 1]))))
            # Escape resume content so it stays text, including links and angle brackets.
            body = escape(line.translate(str.maketrans({'–': '-', '—': '-', '‑': '-'})))
            html += f'<p class="work-title">{body}</p>' if heading else f'<p>{body}</p>'
    css = '''body { font-family: sans-serif; font-size: 10pt; line-height: 1.45; color: #182234; }
h1 { font-size: 23pt; margin: 0 0 3pt; }
h2 { font-size: 12pt; margin: 15pt 0 6pt; border-bottom: 1pt solid #cbd3df; padding-bottom: 3pt; }
p { margin: 0 0 5pt; } .contact { color: #46536b; } .work-title { font-weight: bold; margin-top: 8pt; }'''
    buf = BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    page = pymupdf.Rect(0, 0, 595, 842)
    story = pymupdf.Story(html, user_css=css)
    story.write(writer, lambda n, filled: (page, pymupdf.Rect(46, 42, 549, 800), None))
    writer.close()
    return buf.getvalue()
