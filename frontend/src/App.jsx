import { useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, ArrowRight, ArrowUpRight, Briefcase, Check, CheckCircle, Checks, Copy,
  EnvelopeSimple, FileText, Folder, GearSix, MagnifyingGlass, PaperPlaneTilt, Plus,
  UploadSimple, UserCircle, Users, X,
} from '@phosphor-icons/react'
import { request } from './api.js'
import { Button, Field, MatchReport, Notice, Profile, safeUrl, Tags } from './components.jsx'
import sampleResume from '../../examples/resume.txt?raw'
import sampleJobs from '../../examples/jobs.json'

const steps = [
  { name: 'Your resume', icon: FileText },
  { name: 'Job match', icon: Briefcase },
  { name: 'Contacts', icon: Users },
  { name: 'Email draft', icon: EnvelopeSimple },
]
const titles = ['Let your experience do the talking.', 'See how your resume fits.', 'Reach the right person.', 'Make your first line count.']
const subtitles = ['Upload your resume and we’ll turn it into a clear profile to help you find the right opportunities and write personalized cold emails.',
  'Compare a job description with your resume, review your match, then find the right people to contact.',
  'A relevant contact matters more than a long list of email addresses.',
  'A personal, grounded introduction. Ready for you to review and copy.']

export default function App() {
  const [step, setStep] = useState(0)
  const [candidate, setCandidate] = useState(null)
  const [resumeReport, setResumeReport] = useState(null)
  const [resumeInsights, setResumeInsights] = useState(null)
  const [filename, setFilename] = useState('')
  const [resumeVersion, setResumeVersion] = useState(0)
  const [sample, setSample] = useState(false)
  const [mode, setMode] = useState('company')
  const [target, setTarget] = useState({ role: '', company: '', location: '', job_type: '', job_url: '', job_description: '' })
  const [jobFilename, setJobFilename] = useState('')
  const [contactTarget, setContactTarget] = useState({ company: '', role: '' })
  const [person, setPerson] = useState({ name: '', role: '', email: '' })
  const [job, setJob] = useState(null)
  const [match, setMatch] = useState(null)
  const [opportunities, setOpportunities] = useState([])
  const [contacts, setContacts] = useState([])
  const [selected, setSelected] = useState(null)
  const [domain, setDomain] = useState('')
  const [lookup, setLookup] = useState(false)
  const [patterns, setPatterns] = useState(false)
  const [warnings, setWarnings] = useState([])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [health, setHealth] = useState(null)
  const [settings, setSettings] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [tone, setTone] = useState('Professional')
  const [purpose, setPurpose] = useState('Networking')
  const [context, setContext] = useState('')
  const [email, setEmail] = useState(null)
  const [copied, setCopied] = useState('')
  const fileInput = useRef(null)
  const jobFileInput = useRef(null)
  const heading = useRef(null)
  const targetForm = useRef(null)
  const matchPanel = useRef(null)
  const contactForm = useRef(null)

  useEffect(() => { request('/health').then(setHealth).catch(() => setHealth(false)) }, [])

  useEffect(() => {
    if (match && step === 1) {
      matchPanel.current?.scrollIntoView({ block: 'start' })
      matchPanel.current?.focus({ preventScroll: true })
    }
  }, [match])

  function go(next) {
    const nextTarget = { company: job?.company || contactTarget.company || target.company,
      role: job?.role || (contactTarget.company ? contactTarget.role : target.role) }
    if (next === 2) setContactTarget(nextTarget)
    setStep(next)
    setError('')
    setMessage('')
    window.scrollTo({ top: 0, behavior: 'instant' })
    requestAnimationFrame(() => heading.current?.focus())
    if (next === 2 && step !== 2 && job && mode !== 'person' && !contacts.length && !selected) loadPeople(nextTarget, true)
  }

  function resetResults() {
    setJob(null); setMatch(null); setOpportunities([]); setContacts([]); setSelected(null); setEmail(null); setWarnings([])
  }

  async function run(label, action) {
    setBusy(label); setError(''); setMessage('')
    try { await action() } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  async function upload(file, isSample = false) {
    if (!file || busy) return
    if (!/\.(pdf|docx|txt)$/i.test(file.name) || file.size > 5 * 1024 * 1024 || !file.size) {
      setError('Choose a non-empty PDF, DOCX or TXT file up to 5 MB.'); return
    }
    await run('Reading your resume', async () => {
      const result = await request('/resume/upload', null, file)
      setCandidate(result.profile); setResumeReport(result.health); setFilename(file.name); setSample(isSample)
      setResumeInsights(null)
      if (candidate) resetResults()
      else { setMatch(null); setEmail(null) }
      setResumeVersion(n => n + 1)
      setTarget(prev => ({ ...prev, role: prev.role || result.profile.possible_roles[0] || '' }))
      setMessage('Your profile is ready to review. Correct any details before continuing.')
    })
  }

  async function recheckResume(profile = candidate) {
    await run('Checking your resume', async () => {
      const result = await request('/resume/analyze', { candidate: profile })
      setResumeReport(result.health)
    })
  }

  async function uploadJob(file) {
    if (!file || busy) return
    if (!/\.(pdf|docx)$/i.test(file.name) || file.size > 5 * 1024 * 1024 || !file.size) {
      setError('Choose a non-empty PDF or Word (.docx) file up to 5 MB.'); return
    }
    await run('Reading your job description', async () => {
      const result = await request('/jobs/upload', null, file)
      updateTarget('job_description', result.text)
      setJobFilename(file.name)
      setMessage('Job description loaded. Review or edit the text before getting your match score.')
    })
  }

  async function getResumeInsights() {
    await run('Reviewing your resume with AI', async () => {
      const result = await request('/resume/insights', { candidate })
      setResumeInsights(result.insights)
    })
  }

  async function downloadResume() {
    await run('Preparing your resume PDF', async () => {
      const response = await fetch('/api/resume/download', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate }) })
      if (!response.ok) throw new Error('The resume download could not be prepared. Try again.')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url; link.download = 'reviewed-resume.pdf'; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    })
  }

  async function saveProfile(profile) {
    setCandidate(profile); setResumeReport(null); setResumeInsights(null); resetResults()
    await recheckResume(profile)
  }

  function updateTarget(key, value) {
    setTarget(prev => ({ ...prev, [key]: value })); resetResults()
    if (key === 'job_description') setJobFilename('')
    if (key === 'company' || key === 'role') setContactTarget(prev => ({ ...prev, [key]: value }))
  }

  function updateContactTarget(key, value) {
    setContactTarget(prev => ({ ...prev, [key]: value })); resetResults(); setPurpose('Networking')
    setTarget(prev => ({ ...prev, [key]: value, job_description: '', job_url: '' }))
    setJobFilename('')
    if (key === 'company') { setPerson({ name: '', role: '', email: '' }); setDomain('') }
  }

  function updatePerson(key, value) {
    setPerson(prev => ({ ...prev, [key]: value })); setContacts([]); setSelected(null); setEmail(null)
  }

  function newApplication() {
    setCandidate(null); setResumeReport(null); setResumeInsights(null); setFilename(''); setSample(false); resetResults()
    setPerson({ name: '', role: '', email: '' }); setMode('company')
    setTarget({ role: '', company: '', location: '', job_type: '', job_url: '', job_description: '' })
    setJobFilename('')
    setContactTarget({ company: '', role: '' }); setPurpose('Networking')
    setDomain(''); setLookup(false); setPatterns(false); setContext(''); setTone('Professional'); setCopied(''); setSettings(false)
    go(0)
  }

  function changeMode(value) { setMode(value); resetResults(); setError('') }

  async function findJobs(e) {
    e.preventDefault()
    if (target.role.trim().length < 2 || (mode !== 'discover' && target.company.trim().length < 2)) {
      setError(mode === 'discover' ? 'Enter a target role before searching for opportunities.' : 'Enter a target role and company name before continuing.'); return
    }
    if (mode === 'company' && !target.job_description.trim()) {
      setError('Paste or upload the job description to get a job-specific match score. Use Find opportunities to search for a listing.'); return
    }
    if (mode === 'person' && !target.job_description.trim() && !target.job_url.trim()) {
      setContactTarget({ company: target.company.trim(), role: target.role.trim() })
      setSelected({ ...person, company: target.company.trim(), email_status: 'Unknown', email_source: 'User supplied', warnings: [], email_checks: {}, inferred_emails: [] })
      setPurpose('Networking'); go(3); return
    }
    await run(mode === 'discover' ? 'Finding readable job listings' : 'Comparing your profile', async () => {
      if (mode === 'discover') {
        const result = await request('/jobs/search', { candidate, target_role: target.role,
          company: target.company, location: target.location, job_type: target.job_type })
        setOpportunities(result.opportunities); setWarnings(result.warnings)
        if (!result.opportunities.length) setMessage('No readable listings found. You can still open Contacts and connect with people at a company.')
        return
      }
      const result = await request('/match', { candidate, job: {
        company: target.company.trim(), role: target.role.trim(), job_url: target.job_url.trim(),
        job_description: target.job_description.trim(), location: target.location, source: sampleJobs.some(item => item.company === target.company && item.role === target.role && item.job_description === target.job_description) ? 'Classroom example (fictional)' : 'User supplied',
      } })
      setJob(result.job); setMatch(result.match); setOpportunities([])
      setPurpose('Job application')
      setMessage('Comparison complete. Review the skill matches and gaps below.')
    })
  }

  function chooseJob(item) {
    setJob(item.job); setMatch(item.match); setContacts([]); setSelected(null); setEmail(null)
    setContactTarget({ company: item.job.company, role: item.job.role }); setPurpose('Job application')
    setMessage('Job selected. Your match breakdown is below.')
  }

  function useSampleJob() {
    setMode('company'); resetResults()
    setJobFilename('')
    setContactTarget({ company: sampleJobs[0].company, role: sampleJobs[0].role })
    setTarget({ ...target, role: sampleJobs[0].role, company: sampleJobs[0].company,
      job_description: sampleJobs[0].job_description, job_url: '' })
    setMessage('Fictional classroom job loaded. Click Get match score to compare it with your resume.')
  }

  async function findPeople(e) {
    e.preventDefault()
    await loadPeople(contactTarget)
  }

  async function loadPeople(companyTarget, automatic = false) {
    const suppliedPerson = !automatic && person.name.trim() ? { ...person, company: companyTarget.company } : null
    if (automatic) { setPerson({ name: '', role: '', email: '' }); setDomain(''); setLookup(false); setPatterns(false) }
    await run(suppliedPerson ? 'Reviewing the supplied contact' : 'Finding relevant people', async () => {
      setWarnings([])
      const result = await request('/contacts/find', { company: companyTarget.company, target_role: companyTarget.role || 'career opportunities',
        company_domain: automatic ? '' : domain, person: suppliedPerson,
        find_email: automatic ? false : lookup, allow_patterns: automatic ? false : patterns })
      setContacts(result.contacts); setWarnings(result.warnings); setSelected(null); setEmail(null)
      if (result.company_domain) setDomain(result.company_domain)
      if (result.contacts.length === 1) setSelected(result.contacts[0])
      if (!result.contacts.length) setWarnings(prev => [...prev, 'We couldn’t confirm employees from this search. This doesn’t mean the company has no relevant people. Broaden your search or add someone you know.'])
    })
  }

  async function draft() {
    await run('Writing your introduction', async () => {
      const result = await request('/email/generate', { candidate, job: outreach, employee: selected, tone, purpose, company_context: context })
      setEmail(result.email); setMatch(result.match); setCopied('')
    })
  }

  async function findContactEmail(contact) {
    await run(`Finding and checking email for ${contact.name}`, async () => {
      const result = await request('/contacts/find', { company: contact.company,
        target_role: contactTarget.role || 'career opportunities', company_domain: domain,
        person: contact, find_email: true, allow_patterns: true })
      const updated = { ...result.contacts[0], source: contact.source }
      setContacts(prev => prev.map(item => item === contact ? updated : item))
      if (selected === contact) setSelected(updated)
      if (result.company_domain) setDomain(result.company_domain)
      setWarnings(result.warnings)
      if (!updated.email && !result.warnings.length) setWarnings([`No address was confirmed for ${contact.name}. Review the contact notes for lookup and pattern-check results.`])
    })
  }

  async function copy(text, label) {
    try { await navigator.clipboard.writeText(text); setCopied(label) }
    catch { setError('Clipboard access is unavailable. Select the draft text and copy it manually.') }
  }

  const allowed = [true, !!candidate, true, !!candidate && !!selected]
  const outreach = job || { company: contactTarget.company, role: contactTarget.role || 'career opportunities',
    job_description: '', source: 'Company outreach; no job listing supplied' }
  const hasSampleData = sample || job?.source?.toLowerCase().includes('fictional')

  return <div className="app-shell">
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <header className="topbar">
      <a className="brand" href="#" onClick={e => { e.preventDefault(); if (!busy) go(0) }} aria-label="CareerBridge AI home">
        <PaperPlaneTilt size={34} /><span>CareerBridge AI</span>
      </a>
      <nav className="journey" aria-label="Application stages">{steps.map(({ name, icon: Icon }, i) => i === 1 && !candidate ? null : <button key={name} aria-label={name} disabled={!allowed[i] || !!busy} onClick={() => go(i)} className={step === i ? 'current' : [!!candidate, !!match, !!selected, !!email][i] ? 'complete' : ''} aria-current={step === i ? 'page' : undefined}>
          <span aria-hidden="true">{[!!candidate, !!match, !!selected, !!email][i] && step !== i ? <Check size={15} weight="bold" /> : <Icon size={17} />}</span><strong>{name}</strong>
      </button>)}</nav>
      <Button className="new-button" disabled={!!busy} onClick={newApplication}><Plus size={18} />New application</Button>
    </header>
      <main id="workspace" className={`workspace stage-${step}`}>
        <div className="page-heading"><h1 ref={heading} tabIndex={-1}>{titles[step]}</h1><p>{subtitles[step]}</p></div>

        {settings && <section className="paper connection-panel"><div className="section-head"><h2>Connections</h2><button className="icon-button" aria-label="Close connections" onClick={() => setSettings(false)}><X size={20} /></button></div>
          <p>Local analysis works without provider keys. Live discovery and drafting use your configured accounts.</p>
          <div className="connection-list">{[['Local NLP', health && health.embeddings_installed], ['Job & people search', health?.providers_configured?.TAVILY_API_KEY], ['Hunter email lookup', health?.providers_configured?.HUNTER_API_KEY], ['Apollo fallback', health?.providers_configured?.APOLLO_API_KEY], ['Email writer', health?.providers_configured?.LLM_API_KEY]].map(([name, ready]) => <div key={name}><span>{name}</span><strong>{ready ? 'Configured' : 'Setup needed'}</strong></div>)}</div>
          <p className="muted">Configuration does not guarantee API access. Provider keys and the writer model are managed in the project’s .env file.</p>
          <Button secondary disabled={!!busy} onClick={() => run('Checking connections', async () => setHealth(await request('/health')))}>Refresh connection status</Button>
        </section>}
        {health === false && <Notice error>The backend is unavailable. Start the backend on port 8000 and refresh this page.</Notice>}
        {hasSampleData && <div className="sample-notice"><Notice>{step === 0 ? 'Classroom sample · Fictional candidate' : 'Classroom sample · Includes fictional candidate or job data'}</Notice></div>}
        {error && <Notice error>{error}</Notice>}
        {message && <div className={`status-message ${step === 0 ? 'sr-only' : ''}`} role="status"><CheckCircle size={18} />{message}</div>}
        {busy && <div className="loading-state" role="status" aria-live="polite"><div className="loading-line" /><span>{busy}…</span><small>This may take a moment. Your current results stay here.</small></div>}

        <div className="content-grid application-sheet">
          <div className="primary-column" aria-busy={!!busy}>
            {step === 0 && <>
              <section className="paper upload-paper"><h2>Your resume</h2>
                <p className="section-description">Upload your resume to get started.</p>
                <div className={`upload-zone ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); if (!busy) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); upload(e.dataTransfer.files[0]) }}>
                  <UploadSimple size={32} />
                  <input ref={fileInput} type="file" accept=".pdf,.docx,.txt" aria-label="Choose resume file" className="file-input" disabled={!!busy} onChange={e => { upload(e.target.files[0]); e.target.value = '' }} />
                  <button className="upload-button" disabled={!!busy} onClick={() => fileInput.current.click()}>Choose resume</button><small>PDF, DOCX or TXT · Max 5 MB</small>
                </div>
                {candidate && <div className="uploaded-file"><FileText size={24} /><div><strong>{filename}</strong><span>Uploaded successfully</span></div><CheckCircle size={22} /></div>}
                {!candidate && <div className="sample-row"><span>Just looking around?</span><button className="text-button" disabled={!!busy} onClick={() => upload(new File([sampleResume], 'sample-resume.txt', { type: 'text/plain' }), true)}>Try a sample resume <ArrowUpRight size={15} /></button></div>}
                <section className="review-guide"><h3>Review your details</h3><p>We’ll extract the key information from your resume. Make sure everything looks correct before you continue.</p>
                  <ul>{[['Personal information', candidate?.name || candidate?.email], ['Education details', candidate?.education.length], ['Skills and projects', candidate?.normalized_skills.length && candidate?.projects.length]].map(([label, found]) => <li key={label} className={found ? 'found' : ''}><CheckCircle size={24} weight={found ? 'fill' : 'regular'} /><span>{label} {found ? 'found' : 'to review'}</span></li>)}</ul>
                  {!!candidate?.warnings.length && <details className="small-details"><summary>Extraction notes</summary>{candidate.warnings.map((warning, i) => <p key={i}>{warning}</p>)}</details>}
                </section>
              </section>
            </>}

            {step === 1 && <>
              <section className="paper target-paper">
                <div className="mode-tabs" role="group" aria-label="Targeting mode">{[['company', 'I know the company'], ['discover', 'Find opportunities'], ['person', 'I know the person']].map(([value, label]) => <button key={value} disabled={!!busy} className={mode === value ? 'selected' : ''} onClick={() => changeMode(value)} aria-pressed={mode === value}>{label}</button>)}</div>
                <div className="section-head"><h2>{mode === 'company' ? 'Compare with a job description' : mode === 'discover' ? 'Find an opportunity' : 'Connect with someone you know'}</h2></div>
                <p className="section-description">{mode === 'company' ? 'Add the role, company and responsibilities. Your score shows how your reviewed experience fits this specific job.' : mode === 'discover' ? 'Search for listings, select an opportunity, then review its match score and find contacts.' : 'Enter the company and your contact. Add a job description if you also want a match score.'}</p>
                <form ref={targetForm} onSubmit={findJobs}><fieldset disabled={!!busy}>
                  <div className="form-grid"><Field label="Target role" value={target.role} onChange={e => updateTarget('role', e.target.value)} required minLength={2} placeholder="e.g. Data Analyst" />
                    <Field label={mode === 'discover' ? 'Preferred company (optional)' : 'Company'} value={target.company} onChange={e => updateTarget('company', e.target.value)} required={mode !== 'discover'} minLength={2} placeholder="Company name" /></div>
                  {mode === 'discover' ? <div className="form-grid"><Field label="Location (optional)" value={target.location} onChange={e => updateTarget('location', e.target.value)} placeholder="City or remote" /><Field label="Job type (optional)" value={target.job_type} onChange={e => updateTarget('job_type', e.target.value)} placeholder="Internship, graduate, full-time…" /></div>
                    : <><Field label={mode === 'company' ? 'Job description' : 'Job description (optional)'} multiline rows={8} value={target.job_description} onChange={e => updateTarget('job_description', e.target.value)} required={mode === 'company'} placeholder="Paste the responsibilities, required skills and qualifications from the job listing." hint={mode === 'company' ? 'We compare this description directly with your resume. A company name alone cannot produce a job-specific score.' : 'Leave blank to write a networking introduction without a job match.'} />
                      <div className="job-upload"><Button type="button" secondary onClick={() => jobFileInput.current?.click()}><UploadSimple size={18} />Upload PDF or Word</Button><span>{jobFilename ? `Loaded: ${jobFilename}` : 'PDF or DOCX · Max 5 MB'}</span>
                        <input ref={jobFileInput} type="file" accept=".pdf,.docx" aria-label="Choose job description file" className="file-input" onChange={e => { uploadJob(e.target.files[0]); e.target.value = '' }} /></div>
                      <details className="small-details job-source"><summary>Add a job link (optional)</summary><Field label="Job link (optional)" value={target.job_url} onChange={e => updateTarget('job_url', e.target.value)} type="url" placeholder="https://company.com/careers/…" hint="The description above takes precedence over this link." /></details></>}
                  {mode === 'person' && <div className="recipient-fields"><h4>Your known contact</h4><div className="form-grid"><Field label="Employee name" value={person.name} onChange={e => updatePerson('name', e.target.value)} required placeholder="Full name" /><Field label="Employee role" value={person.role} onChange={e => updatePerson('role', e.target.value)} placeholder="Their job title" /></div><Field label="Professional email" type="email" value={person.email} required onChange={e => updatePerson('email', e.target.value)} placeholder="name@company.com" /></div>}
                  <div className="form-footer"><Button type="submit"><MagnifyingGlass size={18} />{mode === 'discover' ? 'Find opportunities' : mode === 'person' && !target.job_description.trim() && !target.job_url.trim() ? 'Write my introduction' : 'Get match score'}</Button>
                    <button type="button" className="text-button" onClick={useSampleJob}>Use a classroom job</button></div>
                </fieldset></form>
                {mode !== 'person' && <div className="section-action"><span>Just looking to connect? You can find people without a job listing.</span><button className="text-button" disabled={!!busy} onClick={() => go(2)}>Go directly to contacts <ArrowRight size={17} /></button></div>}
              </section>
              {warnings.map((warning, i) => <Notice key={i}>{warning}</Notice>)}
              {!!opportunities.length && <section className="paper opportunity-paper"><h2>Opportunities to consider</h2><p className="section-description">Ranked using your profile and readable job descriptions.</p>
                {opportunities.map((item, i) => <article className={`opportunity ${job?.job_url === item.job.job_url && job?.role === item.job.role ? 'chosen' : ''}`} key={item.id || i}>
                  <div className="company-monogram" aria-hidden="true">{item.job.company.slice(0, 1)}</div><div className="opportunity-info"><h3>{item.job.role}</h3><p>{item.job.company}{item.job.location && ` · ${item.job.location}`}</p><Tags items={item.match.strong_matches.slice(0, 4)} empty="No shared skills identified" />{item.job.job_url && <a href={safeUrl(item.job.job_url)} target="_blank" rel="noreferrer">View listing <ArrowUpRight size={13} /></a>}</div>
                  <div className="opportunity-score"><strong>{item.match.score == null ? '—' : `${Math.round(item.match.score)}%`}</strong><span>Job-specific match</span><Button secondary disabled={!!busy} onClick={() => chooseJob(item)}>Select job</Button></div>
                </article>)}
              </section>}
              {match && job && <div ref={matchPanel} className="job-match-result" tabIndex={-1} aria-label="Job-specific match result"><MatchReport job={job} match={match} nextLabel={mode === 'person' ? 'Write my introduction' : 'Find contacts'} disabled={!!busy} onNext={() => { if (mode === 'person') { if (!targetForm.current.reportValidity()) return; setSelected({ ...person, company: job.company, email_status: 'Unknown', email_source: 'User supplied', warnings: [], email_checks: {}, inferred_emails: [] }); go(3) } else go(2) }} /></div>}
            </>}

            {step === 2 && <>
              <section className="paper contact-paper"><div className="section-head"><h2>Find a relevant contact</h2><Users size={21} className="muted" /></div>
                <p className="section-description">Connect with employees for career advice, placements or referrals. No job listing or match is required.</p>
                <form ref={contactForm} onSubmit={findPeople}><fieldset disabled={!!busy}>
                  <div className="form-grid"><Field label="Company" value={contactTarget.company} onChange={e => updateContactTarget('company', e.target.value)} required minLength={2} placeholder="Company name" />
                    <Field label="Role or area of interest (optional)" value={contactTarget.role} onChange={e => updateContactTarget('role', e.target.value)} minLength={2} placeholder="e.g. Data Science, Frontend Development" hint="Helps us rank people in the relevant team. Leave blank for general career contacts." /></div>
                  <div className="form-grid"><Field label="Employee name (optional)" value={person.name} onChange={e => updatePerson('name', e.target.value)} placeholder="Skip discovery if you know them" /><Field label="Employee role (optional)" value={person.role} onChange={e => updatePerson('role', e.target.value)} placeholder="e.g. Analytics Manager" /></div>
                  <Field label="Known email (optional)" type="email" value={person.email} onChange={e => updatePerson('email', e.target.value)} placeholder="name@company.com" />
                  <label className="check-field"><input type="checkbox" checked={lookup} onChange={e => setLookup(e.target.checked)} />Find and verify professional emails</label>
                  <p className="field-hint">Search finds people first. Enable email lookup to use Hunter, with Apollo as a fallback. Provider credits may be used.</p>
                  {lookup && <><p className="section-description">We find the company domain automatically using company lookup and public web sources.</p>
                    <details className="small-details"><summary>Override company domain (optional)</summary><Field label="Company email domain override" value={domain} onChange={e => setDomain(e.target.value)} placeholder="e.g. company.com" hint="Only use this to replace an automatically found domain." /></details>
                    <label className="check-field"><input type="checkbox" checked={patterns} onChange={e => setPatterns(e.target.checked)} />Try name-based email patterns if no address is found</label>
                    <p className="field-hint">Patterns are checked with Hunter when configured. Guesses and catch-all results remain unconfirmed.</p></>}
                  <div className="form-footer"><Button type="submit"><MagnifyingGlass size={17} />{person.name.trim() ? 'Review this contact' : 'Find relevant people'}</Button>
                    {person.name.trim() && <button className="text-button" type="button" onClick={() => { if (!contactForm.current.reportValidity()) return; setSelected({ ...person, company: contactTarget.company, email_status: 'Unknown', email_source: 'User supplied', warnings: [], email_checks: {}, inferred_emails: [] }); go(candidate ? 3 : 0) }}>Use this person directly <ArrowRight size={16} /></button>}</div>
                </fieldset></form>
              </section>
              {warnings.map((warning, i) => <Notice key={i}>{warning}</Notice>)}
              {!!contacts.length && <section className="paper people-list"><h2>Your contact shortlist</h2><p className="section-description">Find email looks up a work address and checks name-based patterns when needed. Provider credits may be used. Relevance reflects role suitability.</p>
                {domain && <p className="section-description">Company email domain: <strong>{domain}</strong></p>}
                {contacts.map((contact, i) => <article key={i} className={`contact-row ${selected === contact ? 'chosen' : ''}`}><div className="contact-avatar" aria-hidden="true">{contact.name.split(' ').map(word => word[0]).slice(0, 2).join('')}</div>
                  <div className="contact-info"><h3>{contact.name}</h3><p>{contact.role || 'Role not supplied'} · {contact.company}</p><p className="contact-email">{contact.email || 'No email address yet'} <span className="email-status">{contact.email_status}</span></p>
                    {!!contact.inferred_emails?.length && <details className="small-details"><summary>Email patterns and checks</summary>{contact.inferred_emails.map(address => <p key={address}>{address} · {contact.email_checks?.pattern_checks?.[address] || 'Not checked'}</p>)}</details>}
                    {contact.profile_url && <a href={safeUrl(contact.profile_url)} target="_blank" rel="noreferrer">Public source <ArrowUpRight size={13} /></a>}
                    {contact.evidence && <details className="small-details"><summary>Why this person was found</summary><p>{contact.evidence}</p></details>}
                    {(!!contact.warnings?.length || !!Object.keys(contact.email_checks || {}).length) && <details className="small-details"><summary>Contact notes and verification</summary>{contact.email && contact.email_source && <p>Email source: {contact.email_source}</p>}{[...new Set(contact.warnings || [])].map((text, n) => <p key={n}>{text}</p>)}{Object.entries(contact.email_checks || {}).map(([key, value]) => <p key={key}>{key.replaceAll('_', ' ')}: {typeof value === 'object' ? JSON.stringify(value) : String(value)}</p>)}</details>}
                  </div><div className="contact-selection">{contact.relevance_score != null && <span>{Math.round(contact.relevance_score)}% relevance</span>}<div className="contact-actions">{!contact.email && <Button secondary disabled={!!busy} aria-label={`Find email for ${contact.name}`} onClick={() => findContactEmail(contact)}><EnvelopeSimple size={16} />Find email</Button>}<Button secondary disabled={!!busy} onClick={() => { setSelected(contact); setEmail(null) }}>{selected === contact ? <><Check size={16} />Selected</> : 'Choose contact'}</Button></div></div>
                </article>)}
                {selected && <div className="section-action"><span>{candidate ? 'Email lookup is optional. You can write a draft without an address.' : 'Add your resume so the draft can use your real experience.'}</span><Button disabled={!!busy} onClick={() => go(candidate ? 3 : 0)}>{candidate ? 'Write my introduction' : 'Add my resume'} <ArrowRight size={17} /></Button></div>}
              </section>}
              {!contacts.length && <section className="quiet-section"><h3>Who should you contact?</h3><p>Start with a manager in the relevant department, a recruiter, or a team lead. Public-source results will include evidence so you can confirm their role.</p></section>}
            </>}

            {step === 3 && <>
              <section className="paper email-paper"><div className="section-head"><h2>Your introduction</h2><span className="source-label">Draft only</span></div>
                <div className="recipient-line"><span>To</span><div><strong>{selected.name || 'Company contact'}</strong><p>{selected.role || 'Role not supplied'} · {outreach.company}</p></div><span className="email-status">{selected.email_status || 'Unknown'}</span></div>
                <p className="recipient-email">{selected.email || 'No email address supplied. You can still generate a draft.'}</p>
                <div className="form-grid"><label className="field"><span>Tone</span><select value={tone} disabled={!!busy} onChange={e => { setTone(e.target.value); setEmail(null) }}>{['Professional', 'Concise', 'Friendly', 'Technical'].map(value => <option key={value}>{value}</option>)}</select></label>
                  <label className="field"><span>Email purpose</span><select value={purpose} disabled={!!busy} onChange={e => { setPurpose(e.target.value); setEmail(null) }}><option value="Networking">Networking and career advice</option><option value="Referral">Referral or placement guidance</option>{job?.job_description && <option value="Job application">Job application</option>}</select></label></div>
                <div className="target-summary"><span>Area of interest</span><strong>{outreach.role}</strong></div>
                <details className="context-details"><summary>Add company context (optional)</summary><Field label="Useful company context" multiline rows={3} value={context} onChange={e => { setContext(e.target.value); setEmail(null) }} maxLength={3000} disabled={!!busy} placeholder="Add a relevant product, team, or public project. Include only information you can support." /></details>
                {!email && <div className="draft-empty"><EnvelopeSimple size={32} /><h3>Write from what’s real.</h3><p>{job?.job_description ? 'Your reviewed profile, selected contact and job context will guide the draft.' : 'Your reviewed skills and projects will guide an introduction asking about advice or referrals. No vacancy is assumed.'}</p><Button onClick={draft} disabled={!!busy}><PaperPlaneTilt size={18} />Generate my email</Button><small>Selected profile, company and contact details go to your configured writing provider.</small></div>}
                {email && <div className="draft-content"><div className="draft-subject"><span>Subject</span><h3>{email.subject}</h3><button className="icon-button" onClick={() => copy(email.subject, 'subject')} aria-label="Copy subject">{copied === 'subject' ? <Check size={20} /> : <Copy size={20} />}</button></div>
                  <div className="email-body" tabIndex={0}>{email.body}</div><div className="draft-actions"><Button onClick={() => copy(email.body, 'email')}>{copied === 'email' ? <><Checks size={18} />Copied email</> : <><Copy size={18} />Copy email</>}</Button><Button secondary disabled={!!busy} onClick={draft}>Regenerate draft</Button></div>
                  <p className="draft-reminder">Check names, facts and claims before you send it yourself.</p></div>}
              </section>
              <div className="back-row"><button className="text-button" disabled={!!busy} onClick={() => go(mode === 'person' ? 1 : 2)}><ArrowLeft size={16} />Change recipient or role</button></div>
            </>}
          </div>

          {step === 0 ? (candidate ? <Profile key={resumeVersion} candidate={candidate} report={resumeReport} insights={resumeInsights} onInsights={getResumeInsights} onDownload={downloadResume} reviewing={busy === 'Reviewing your resume with AI'} disabled={!!busy} onRecheck={() => recheckResume()} onMatch={() => go(1)} onNext={() => go(2)} onSave={saveProfile} />
            : <section className="paper profile-paper empty-profile"><h2>Candidate profile</h2><div><Folder size={36} /><h3>Your experience, ready to review.</h3><p>Choose a resume or try the classroom sample. Your education, skills and projects will appear here.</p></div></section>) : <aside className="context-column" aria-label="Application context">
            <h2>Your application</h2>
            {candidate && <section className="candidate-context"><div className="context-heading"><UserCircle size={20} /><h3>Your profile</h3></div><strong>{candidate.name || 'Reviewed candidate'}</strong><p>{candidate.education[0] || 'Education not supplied'}</p><Tags items={candidate.normalized_skills.slice(0, 5)} />{candidate.normalized_skills.length > 5 && <span className="muted">+{candidate.normalized_skills.length - 5} more skills</span>}<button className="text-button" disabled={!!busy} onClick={() => go(0)}>Review profile <ArrowUpRight size={15} /></button></section>}
            {job && <section className="selected-job-context"><div className="context-heading"><Briefcase size={19} /><h3>Selected opportunity</h3></div><strong>{job.role}</strong><p>{job.company}</p><div><span>Local match</span><strong>{match?.score == null ? 'Unavailable' : `${Math.round(match.score)}%`}</strong></div></section>}
            {!job && contactTarget.company && <section className="selected-job-context"><div className="context-heading"><Users size={19} /><h3>Your outreach</h3></div><strong>{contactTarget.company}</strong><p>{contactTarget.role || 'General career contacts'}</p><p>Networking and referrals · No listing required</p></section>}
          </aside>}
        </div>
        <footer className="workspace-footer"><p>ATS checks run locally. AI insights and drafts use your configured provider.</p><button className="text-button" onClick={() => setSettings(!settings)} aria-expanded={settings}><GearSix size={16} />Connections</button></footer>
      </main>
  </div>
}
