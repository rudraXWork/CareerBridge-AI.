import { useRef, useState } from 'react'
import { ArrowClockwise, ArrowRight, Check, EnvelopeSimple, Folder, GraduationCap, Info, Note, PencilSimple, WarningCircle, Wrench } from '@phosphor-icons/react'
import { groupProjects } from './projects.js'
import { rewriteProblem } from './insights.js'

export function Button({ children, secondary = false, className = '', ...props }) {
  return <button className={`button ${secondary ? 'secondary' : ''} ${className}`} {...props}>{children}</button>
}

export function Field({ label, hint, multiline = false, ...props }) {
  return <label className="field">
    <span>{label}</span>
    {multiline ? <textarea {...props} /> : <input {...props} />}
    {hint && <small>{hint}</small>}
  </label>
}

export function Notice({ children, error = false }) {
  return <div className={`notice ${error ? 'error' : ''}`} role={error ? 'alert' : 'status'}>
    {error ? <WarningCircle size={19} /> : <Info size={19} />}
    <div>{children}</div>
  </div>
}

export function Tags({ items, empty = 'None identified', kind = '' }) {
  return <div className={`tags ${kind}`}>
    {items.length ? items.map(item => <span key={item}>{item}</span>) : <p className="muted">{empty}</p>}
  </div>
}

export function Profile({ candidate, report, insights, onInsights, onDownload, reviewing, onRecheck, onSave, onMatch, onNext, disabled }) {
  const [editing, setEditing] = useState(false)
  const editButton = useRef(null)
  const lines = text => text.split('\n').map(line => line.trim()).filter(Boolean)
  const role = candidate.summary.match(/^(.+?student)\b/i)?.[1] || candidate.possible_roles[0] || 'Your reviewed profile'
  const summary = candidate.summary.startsWith(role) ? candidate.summary.slice(role.length).trim().replace(/^./, c => c.toUpperCase()) : candidate.summary
  return <section className="paper profile-paper">
    <ResumeHealth report={report} insights={insights} onInsights={onInsights} reviewing={reviewing} onRecheck={onRecheck} disabled={disabled} />
    <div className="section-head"><h2>Candidate profile</h2><div className="profile-tools"><Button secondary disabled={disabled} onClick={onDownload}>Download resume PDF</Button><Button ref={editButton} secondary disabled={disabled} aria-expanded={editing} onClick={() => setEditing(!editing)}><PencilSimple size={19} />{editing ? 'Close editor' : 'Edit details'}</Button></div></div>
    <p className="health-note">The PDF uses your reviewed profile in a simple text layout.</p>
    <div className="profile-identity">
      <h3>{candidate.name || 'Name not identified'}</h3><p>{role}</p>
      <span><EnvelopeSimple size={18} />{candidate.email || 'Email not identified'}</span>
    </div>
    <div className="profile-detail"><GraduationCap size={24} /><div><h4>Education</h4>
      {candidate.education.length ? candidate.education.map((item, i) => <p key={i}>{item}</p>) : <p className="muted">No education section identified.</p>}</div>
    </div>
    <div className="profile-detail"><Note size={24} /><div><h4>Profile summary</h4><p>{summary || 'No summary identified. Add one with Edit details.'}</p></div></div>
    <div className="profile-detail"><Wrench size={24} /><div><h4>Skills</h4><Tags items={candidate.normalized_skills} /></div></div>
    <div className="profile-detail project-details"><Folder size={24} /><div><h4>Projects</h4>{candidate.projects.length ? groupProjects(candidate.projects).map((project, i) =>
      <div className="project-entry" key={i}>{project.title && <h5>{project.title}</h5>}
        {project.tools && <p className="project-tools">{project.tools}</p>}
        {!!project.bullets.length && <ul>{project.bullets.map((text, n) => <li key={n}>{text}</li>)}</ul>}
      </div>
    ) : <p className="muted">No projects identified. You can add them with Edit details.</p>}</div></div>
    {!!candidate.experience.length && <div className="profile-detail project-details"><Folder size={24} /><div><h4>Experience</h4>{groupProjects(candidate.experience).map((entry, i) =>
      <div className="project-entry" key={i}>{entry.title && <h5>{entry.title}</h5>}
        {entry.tools && <p className="project-tools">{entry.tools}</p>}
        {!!entry.bullets.length && <ul>{entry.bullets.map((text, n) => <li key={n}>{text}</li>)}</ul>}
      </div>
    )}</div></div>}
    {editing && <div className="edit-profile">
      <h3>Correct your profile</h3><p className="muted">Saving rechecks this text and clears old job matches. Update and re-upload your file to change its layout.</p>
      <form onSubmit={e => {
        e.preventDefault()
        const form = new FormData(e.currentTarget)
        const skills = form.get('skills').split(',').map(item => item.trim()).filter(Boolean)
        onSave({ ...candidate, name: form.get('name'), email: form.get('email'), summary: form.get('summary'),
          normalized_skills: [...new Set(skills)], skills, technologies: skills,
          education: lines(form.get('education')), projects: lines(form.get('projects')),
          experience: lines(form.get('experience')), certifications: lines(form.get('certifications')),
          experience_years: form.get('years') === '' ? null : Number(form.get('years')) })
        setEditing(false)
        requestAnimationFrame(() => editButton.current?.focus())
      }}>
        <fieldset disabled={disabled}>
          <div className="form-grid"><Field label="Name" name="name" defaultValue={candidate.name} />
            <Field label="Your email" name="email" type="email" defaultValue={candidate.email} /></div>
          <Field label="Summary" multiline name="summary" defaultValue={candidate.summary} rows={3} />
          <Field label="Reviewed skills" name="skills" defaultValue={candidate.normalized_skills.join(', ')} hint="Separate skills with commas. This list is used for matching." />
          <Field label="Education" multiline name="education" defaultValue={candidate.education.join('\n')} rows={2} />
          <Field label="Projects" multiline name="projects" defaultValue={candidate.projects.join('\n')} rows={4} hint="Put each project title on its own line, followed by its bullet points. You can also use Title: description." />
          <Field label="Experience" multiline name="experience" defaultValue={candidate.experience.join('\n')} rows={3} />
          <Field label="Certifications" multiline name="certifications" defaultValue={candidate.certifications.join('\n')} rows={2} />
          <Field label="Years of professional experience" name="years" type="number" min="0" max="70" step="0.5" defaultValue={candidate.experience_years ?? ''} hint="Leave blank if unknown. Academic projects are considered separately." />
          <Button type="submit"><Check size={17} /> Save corrections</Button>
        </fieldset>
      </form>
    </div>}
    <div className="profile-action"><Button secondary disabled={disabled} onClick={onMatch}>Job match <ArrowRight size={18} /></Button><Button disabled={disabled} onClick={onNext}>Contacts <ArrowRight size={18} /></Button></div>
  </section>
}

function ResumeHealth({ report, insights, onInsights, reviewing, onRecheck, disabled }) {
  const fixes = report ? report.ats.checks.filter(item => item.status === 'review') : []
  const unchecked = report ? report.ats.checks.filter(item => item.points == null) : []
  const atsPoints = report ? Math.round(report.ats.checks.reduce((sum, item) => sum + (item.points ?? 0), 0) * 100) / 100 : 0
  return <section className="resume-health" aria-labelledby="resume-health-title">
    <div className="section-head"><h3 id="resume-health-title">Resume health</h3><Button secondary disabled={disabled} onClick={onRecheck}><ArrowClockwise size={16} />Recheck resume</Button></div>
    {report ? <>
      <p className="section-description">ATS readiness checks parsing and structure. Content quality checks your project and experience statements.</p>
      <dl className="health-scores">{[['Resume health', report.score], ['ATS readiness', report.ats.score], ['Content quality', report.content.score]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value == null ? 'Unavailable' : <>{Math.round(value)}<small> / 100</small></>}</dd></div>)}</dl>
      <p className="health-note">ATS readiness uses {atsPoints} out of {report.ats.coverage} assessed points. {report.ats.coverage}% of the weighted checks were assessed.{!!unchecked.length && <> Not assessed: {unchecked.map(item => item.title).join(', ')}. A score of 100 means all assessed checks passed.</>}</p>
      <p className="health-note">{report.note}</p>
      {!!fixes.length && <ul className="health-findings">{fixes.map(item => <li key={item.id}><h4>{item.title}</h4><FindingText item={item} /></li>)}</ul>}
      <section className="resume-insights" aria-labelledby="resume-insights-title">
        <div className="section-head"><h4 id="resume-insights-title">AI insights</h4><Button disabled={disabled} onClick={onInsights}>{reviewing ? 'Reviewing your resume…' : insights ? 'Refresh AI insights' : 'Generate AI insights'}</Button></div>
        <p className="section-description">Specific feedback and suggested rewrites for your project and experience statements.</p>
        {!insights && <p className="health-note">Uses your extracted work statements and skills with your configured AI provider. Your name, email and original file are not included. Local scores stay unchanged.</p>}
        {insights && <>
          <p className="insight-summary">{insights.summary}</p>
          {!!insights.strengths.length && <div className="insight-strengths"><h5>What’s working</h5><ul>{insights.strengths.map((text, i) => <li key={i}>{text}</li>)}</ul></div>}
          <ol className="insight-list">{insights.improvements.slice(0, 2).map(item => {
            const problem = item.rewrite_note || rewriteProblem(item.original, item.rewrite)
            if (problem && !item.question) return null
            return <li key={item.statement_id}>
            <h5>{item.title}</h5><p>{item.issue}</p>
            <dl className="insight-wording"><div><dt>Original statement</dt><dd>{item.original}</dd></div>{!problem && <div className="insight-rewrite"><dt>Suggested wording</dt><dd>{item.rewrite}</dd></div>}</dl>
            {problem && <p>{problem}</p>}
            {item.question && <p className="insight-question"><strong>Detail to add</strong>{item.question}</p>}
          </li>})}</ol>
          <p className="health-note">Review suggested wording and use Edit details to make changes to your profile.</p>
        </>}
      </section>
      <details className="small-details"><summary>See all checks and score rules</summary>
        <p>Resume health is the average of ATS readiness and content quality. Each uses weighted checks; unassessed checks receive no points and are excluded from the denominator.</p>
        {[['ATS readiness', report.ats], ['Content quality', report.content]].map(([label, group]) => <div key={label}><h4>{label}</h4><ul className="health-checks">{group.checks.map(item => <li key={item.id}><div><strong>{item.title}</strong><span>{item.points == null ? 'Not checked' : `${item.points} / ${item.weight} points`}</span></div><FindingText item={item} /></li>)}</ul></div>)}
      </details>
      <p className="health-note">{report.file_note}</p>
    </> : <p className="section-description">Recheck your resume to see local ATS and content checks.</p>}
  </section>
}

function FindingText({ item }) {
  // Existing reports stay readable until the user rechecks them.
  const old = item.evidence.match(/ (?:Example|Repeated): “(.+)”$/)
  const example = item.example || old?.[1]
  return <>
    <p>{old ? item.evidence.slice(0, old.index) : item.evidence}</p>
    {example && <div className="health-example"><strong>Statement to review</strong><blockquote>{example}</blockquote></div>}
    {item.fix && <p className="health-fix"><strong>How to improve</strong>{item.fix}</p>}
  </>
}

const labels = { skills: 'Skill coverage', semantic: 'Semantic similarity', projects: 'Project relevance', experience: 'Experience', education: 'Education' }

export function MatchReport({ job, match, onNext, disabled, nextLabel = 'Choose a contact' }) {
  return <section className="paper match-paper">
    <div className="section-head"><h2>Job-specific match score</h2><span className="source-label">Local analysis</span></div>
    <p className="section-description">{job.role} · {job.company}. This measures fit with the job description, separately from ATS readiness.</p>
    <div className="match-overview">
      <div><span className="score-label">Resume ↔ selected job</span><p className="match-number">{match.score === null ? '—' : Math.round(match.score)}{match.score !== null && <span>%</span>}</p>
        <p>{match.score === null ? 'More information needed' : 'A comparison, not a hiring prediction'}</p></div>
      <div className="score-components">{Object.entries(labels).map(([key, label]) => <div key={key}>
        <span>{label}</span><div className="score-track" aria-hidden="true"><i style={{ width: `${match.components[key] ?? 0}%` }} /></div>
        <strong>{match.components[key] == null ? '—' : `${Math.round(match.components[key])}%`}</strong>
      </div>)}</div>
    </div>
    <p className="match-explanation">{match.explanation}</p>
    <div className="match-skills"><div><h4>Strong matches</h4><Tags items={match.strong_matches} kind="positive" /></div>
      <div><h4>Missing or weaker</h4><Tags items={[...match.missing_skills, ...match.gaps]} kind="gaps" empty="No gaps identified by these rules" /></div></div>
    <details className="small-details"><summary>See score evidence and job description</summary>
      <p>Evidence coverage: {match.evidence_coverage}%. Available components use these weights:</p>
      <dl className="evidence-list">{Object.entries(match.weights_used).map(([key, value]) => <div key={key}><dt>{labels[key]}</dt><dd>{Math.round(value * 100)}%</dd></div>)}</dl>
      {match.relevant_projects.map((project, i) => <p key={i}><strong>Project relevance {Math.round(project.score)}%: </strong>{project.text}</p>)}
      <h4>Parsed job skills</h4><Tags items={job.required_skills} />
      <h4>Preferred skills</h4><Tags items={job.preferred_skills} />
      <h4>Responsibilities</h4>{job.responsibilities.map((text, i) => <p key={i}>{text}</p>)}
      <h4>Source description</h4><p className="preserve-lines">{job.job_description || 'No full description supplied.'}</p>
      {job.job_url && <a href={safeUrl(job.job_url)} target="_blank" rel="noreferrer">Open source listing <ArrowRight size={14} /></a>}
    </details>
    {match.warnings.map((warning, i) => <Notice key={i}>{warning}</Notice>)}
    <div className="section-action"><span>{nextLabel === 'Write my introduction' ? 'Your supplied contact will be used directly.' : 'We’ll find relevant people using this company and role.'}</span><Button onClick={onNext} disabled={disabled}>{nextLabel} <ArrowRight size={17} /></Button></div>
  </section>
}

export function safeUrl(url) {
  try { const parsed = new URL(url); return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : undefined } catch { return undefined }
}
