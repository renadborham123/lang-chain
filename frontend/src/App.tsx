import { ChangeEvent, useMemo, useState } from 'react'
import { ArrowUpRight, BriefcaseBusiness, CheckCircle2, Download, FileText, MapPin, Play, Search, Sparkles, UploadCloud, X } from 'lucide-react'

type Job = { id: string; title: string; company: string; location: string; description: string; url: string; source: string; score: number; keywords: string[]; status: 'ready' | 'review'; rule_reasons: string[]; direct_listing: boolean; candidate?: string; profile?: Record<string, unknown> }
type SearchData = { profile: Record<string, unknown>; queries: string[]; discovered: number; matched: number; qualified: number; review: number; excluded: number; jobs: Job[] }
type BatchResult = { candidate: string; error: string | null; data: SearchData | null }

const API = 'http://localhost:8000/api'
const CV_QUESTIONS = [
  { key: 'identity', label: '1 / 6', question: 'What is your name, email, phone, city, and LinkedIn/GitHub link?', hint: 'You may leave out any contact detail you do not want to share.' },
  { key: 'goal', label: '2 / 6', question: 'What role are you targeting and what makes you a good fit?', hint: 'Example: Agentic AI Engineer focused on LLM agents and RAG systems.' },
  { key: 'experience', label: '3 / 6', question: 'Tell me about your work experience, freelance work, or internships.', hint: 'Include company/project, your role, dates if known, and what you built.' },
  { key: 'projects', label: '4 / 6', question: 'What are your best AI, LLM, agent, or software projects?', hint: 'Mention the problem, stack, and result—only facts you can defend.' },
  { key: 'skills', label: '5 / 6', question: 'Which technical skills and tools do you actually use?', hint: 'Example: Python, LangGraph, LangChain, Gemini, RAG, Docker, FastAPI.' },
  { key: 'education', label: '6 / 6', question: 'What education, certificates, languages, or achievements should be included?', hint: 'It is okay to write “none yet”; it will be omitted.' },
] as const

function App() {
  const [mode] = useState<'single' | 'batch'>('single')
  const [location, setLocation] = useState('Cairo')
  const [limit, setLimit] = useState(10)
  const [liveBrowser, setLiveBrowser] = useState(false)
  const [targetRoles, setTargetRoles] = useState('Agentic AI Engineer, LLM Engineer, AI Engineer, Applied AI Engineer, Generative AI Engineer')
  const [excludedTitleTerms, setExcludedTitleTerms] = useState('Backend Developer, FastAPI')
  const [singleFile, setSingleFile] = useState<File | null>(null)
  const [generatedCV, setGeneratedCV] = useState('')
  const [cvBuilderOpen, setCvBuilderOpen] = useState(false)
  const [batchFiles, setBatchFiles] = useState<File[]>([])
  const [single, setSingle] = useState<SearchData | null>(null)
  const [batch, setBatch] = useState<BatchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [captchaBlocked, setCaptchaBlocked] = useState(false)
  const [applicationNotice, setApplicationNotice] = useState('')
  const [draft, setDraft] = useState<{ job: Job; text: string } | null>(null)

  const jobs = useMemo(() => mode === 'single'
    ? single?.jobs.map(job => ({ ...job, profile: single.profile })) ?? []
    : batch.flatMap(item => item.data?.jobs.map(job => ({ ...job, candidate: item.candidate, profile: item.data?.profile })) ?? []), [mode, single, batch])
  const totalFound = mode === 'single' ? single?.discovered ?? 0 : batch.reduce((sum, item) => sum + (item.data?.discovered ?? 0), 0)
  const totalMatched = mode === 'single' ? single?.matched ?? 0 : batch.reduce((sum, item) => sum + (item.data?.matched ?? 0), 0)
  const totalQualified = mode === 'single' ? single?.qualified ?? 0 : batch.reduce((sum, item) => sum + (item.data?.qualified ?? 0), 0)

  async function runSearch(forceBackground = false) {
    setError('')
    setCaptchaBlocked(false)
    setApplicationNotice('')
    setLoading(true)
    try {
      const form = new FormData()
      form.append('location', location)
      form.append('limit', String(limit))
      form.append('live_browser', String(forceBackground ? false : liveBrowser))
      form.append('target_roles', targetRoles)
      form.append('excluded_title_terms', excludedTitleTerms)
      let response: Response
      if (mode === 'single') {
        const cvForSearch = singleFile ?? (generatedCV ? new File([generatedCV], 'jobflow-generated-cv.txt', { type: 'text/plain' }) : null)
        if (!cvForSearch) throw new Error('Upload a CV or create one with “I don’t have a CV”.')
        form.append('cv', cvForSearch)
        form.append('user_id', `web-${cvForSearch.name}`)
        response = await fetch(`${API}/search`, { method: 'POST', body: form })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'Search failed')
        setSingle(data)
      } else {
        if (!batchFiles.length) throw new Error('Choose at least one CV.')
        if (batchFiles.length > 10) throw new Error('A batch supports up to 10 CVs.')
        batchFiles.forEach(file => form.append('cvs', file))
        response = await fetch(`${API}/batch-search`, { method: 'POST', body: form })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'Batch search failed')
        setBatch(data.results)
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      setError(message)
      setCaptchaBlocked(message.toLowerCase().includes('captcha'))
    } finally {
      setLoading(false)
    }
  }

  async function prepareApplication(job: Job) {
    const response = await fetch(`${API}/application-draft`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: job.title, company: job.company, keywords: job.keywords, profile: job.profile ?? {} }) })
    const data = await response.json()
    if (!response.ok) { setError(data.detail || 'Could not prepare application'); return }
    setDraft({ job, text: data.message })
  }

  async function openLiveApplication(job: Job) {
    setError('')
    setApplicationNotice('')
    if (!job.direct_listing) {
      window.open(job.url, '_blank', 'noopener,noreferrer')
      return
    }
    try {
      const response = await fetch(`${API}/application-session`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: job.url }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not open the application session')
      setApplicationNotice(data.message)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the application session')
    }
  }

  function filesChosen(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    if (mode === 'single') setSingleFile(files[0] ?? null)
    else setBatchFiles(files.slice(0, 10))
  }

  return <main>
    <aside className="sidebar">
      <div className="brand"><div className="brandmark"><Sparkles size={18}/></div><span>jobflow</span></div>
      <div className="nav-title">WORKSPACE</div>
      <button className="nav-active"><Search size={17}/> Discover jobs</button>
      <button className="nav"><FileText size={17}/> Application drafts</button>
      <div className="side-bottom"><div className="gemini-dot"/> Gemini agent online</div>
    </aside>

    <section className="content">
      <header><div><p className="eyebrow">JOB DISCOVERY SYSTEM</p><h1>Find the right work,<br/><em>without the busywork.</em></h1></div><div className="header-status"><CheckCircle2 size={16}/> Local &amp; private</div></header>
      <section className="control-panel">
        <div className="mode-switch personal-flow"><span className="single-cv-label"><FileText size={17}/> Your CV</span><button className="no-cv-button" onClick={() => setCvBuilderOpen(true)}><Sparkles size={17}/> I don't have a CV — build it with AI</button></div>
        {mode === 'single' && generatedCV && <p className="generated-ready"><CheckCircle2 size={14}/> Generated CV is selected and ready for job search.</p>}
        <div className="setup-grid">
          <label className="upload-zone"><input type="file" accept=".pdf,.txt" multiple={mode === 'batch'} onChange={filesChosen}/><UploadCloud size={23}/><span>{mode === 'single' ? singleFile?.name ?? 'Drop a CV here or browse' : batchFiles.length ? `${batchFiles.length} CVs ready` : 'Drop up to 10 CVs here or browse'}</span><small>PDF or TXT · processed locally before matching</small></label>
          <label className="field"><span>Target location</span><div><MapPin size={16}/><input value={location} onChange={event => setLocation(event.target.value)} placeholder="Cairo or Remote"/></div></label>
          <label className="field short"><span>Jobs per CV</span><select value={limit} onChange={event => setLimit(Number(event.target.value))}>{[3, 5, 10].map(value => <option key={value}>{value}</option>)}</select></label>
          <label className="field role-field"><span>Target roles</span><input value={targetRoles} onChange={event => setTargetRoles(event.target.value)} placeholder="Agentic AI Engineer, LLM Engineer"/></label>
          <label className="field exclude-field"><span>Exclude titles</span><input value={excludedTitleTerms} onChange={event => setExcludedTitleTerms(event.target.value)} placeholder="Backend Developer, FastAPI"/></label>
          <label className="watch-toggle"><input type="checkbox" checked={liveBrowser} onChange={event => setLiveBrowser(event.target.checked)} disabled={mode === 'batch'}/><span>Watch browser live</span><small>{mode === 'batch' ? 'Use one CV for live mode' : 'Opens the Playwright browser while it searches'}</small></label>
          <button className="search-button" onClick={() => runSearch()} disabled={loading}><Play size={17} fill="currentColor"/>{loading ? 'Agents are working...' : mode === 'single' ? 'Find matching jobs' : 'Run parallel agents'}</button>
        </div>
        {error && <p className="error">{error}</p>}
        {captchaBlocked && <button className="captcha-retry" onClick={() => runSearch(true)} disabled={loading}>Retry without live browser</button>}
        {applicationNotice && <p className="notice">{applicationNotice}</p>}
      </section>

      <section className={`pipeline ${loading ? 'running' : ''}`}><span className="pipeline-label">APPLICATION PIPELINE</span><div className="pipeline-steps"><b>1. Discover</b><i/><b>2. Match</b><i/><b>3. Qualify</b><i/><b>4. Rank</b><i/><b>5. Draft</b><i/><b>6. Approve</b></div><p>{loading ? 'Agents are moving through the pipeline now.' : 'Rules remove weak matches before the application agent prepares anything.'}</p></section>
      {jobs.length > 0 && <><section className="results-top"><div><p className="eyebrow">QUALIFIED ROLES</p><h2>{jobs.length} roles ready to review</h2><p>Direct listings can be opened in a visible Playwright browser.</p></div><div className="metrics"><Metric label="DISCOVERED" value={totalFound}/><Metric label="MATCHED" value={totalMatched}/><Metric label="QUALIFIED" value={totalQualified}/><Metric label="TOP SCORE" value={Math.round(Math.max(...jobs.map(job => job.score)) * 100)}/></div></section><Scoreboard jobs={jobs}/><section className="job-grid">{jobs.map((job, index) => <JobCard job={job} key={`${job.candidate ?? 'you'}-${job.id}`} index={index} onPrepare={prepareApplication} onApply={openLiveApplication}/>)}</section></>}
      {!jobs.length && !loading && <section className="empty"><BriefcaseBusiness size={30}/><h2>Your job board will appear here.</h2><p>Upload a CV, choose your role rules, then let the agents build your shortlist.</p></section>}
    </section>
    {draft && <DraftModal draft={draft} onClose={() => setDraft(null)}/>} 
    {cvBuilderOpen && <CVBuilder onClose={() => setCvBuilderOpen(false)} onUse={text => { setGeneratedCV(text); setSingleFile(null); setCvBuilderOpen(false) }}/>} 
  </main>
}

function Metric({ label, value }: { label: string; value: number }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div> }

function Scoreboard({ jobs }: { jobs: Job[] }) {
  const ranked = [...jobs].sort((a, b) => b.score - a.score).slice(0, 5)
  return <section className="scoreboard"><div><p className="eyebrow">MATCH SCORING</p><h3>Why these roles rank higher</h3><p>Score is based on CV skill overlap. Direct listings are separately marked for verification.</p></div><div className="score-list">{ranked.map(job => { const percent = Math.round(job.score * 100); return <div className="score-row" key={job.id}><div className="score-title"><span>{job.title}</span><b>{percent}%</b></div><div className="score-track"><i style={{ width: `${percent}%` }}/></div><small>{job.keywords.length} matched skill{job.keywords.length === 1 ? '' : 's'} · {job.direct_listing ? 'Direct listing' : 'Search lead'}</small></div> })}</div></section>
}

function JobCard({ job, index, onPrepare, onApply }: { job: Job; index: number; onPrepare: (job: Job) => void; onApply: (job: Job) => void }) {
  const statusLabel = job.status === 'ready' ? 'READY TO DRAFT' : 'NEEDS REVIEW'
  const listingLabel = job.direct_listing ? 'DIRECT LISTING' : 'SEARCH LEAD'
  return <article className="job-card" style={{ animationDelay: `${Math.min(index, 8) * 55}ms` }}><div className="job-meta"><span className={`source ${job.direct_listing ? 'direct' : ''}`}>{listingLabel}</span><span className={`status ${job.status}`}>{statusLabel}</span></div>{job.candidate && <p className="candidate">For {job.candidate}</p>}<h3>{job.title}</h3><p className="company">{job.company} <span>•</span> {job.location}</p><p className="description">{job.description || 'Open the listing to learn more about this opportunity.'}</p><div className="keywords">{job.keywords.map(keyword => <span key={keyword}>{keyword}</span>)}</div><p className="rule-reason">{job.rule_reasons[0]}</p><div className="card-actions">{job.status === 'ready' ? <button className="draft-button" onClick={() => onPrepare(job)}>Draft with agent</button> : <button className="draft-button" disabled>Review before drafting</button>}<button className="apply-button" onClick={() => onApply(job)}>{job.direct_listing ? 'Apply live' : 'Open source'} <ArrowUpRight size={16}/></button></div></article>
}

function CVBuilder({ onClose, onUse }: { onClose: () => void; onUse: (text: string) => void }) {
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [text, setText] = useState('')
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState('')
  const current = CV_QUESTIONS[step]

  async function build() {
    setBuilding(true)
    setError('')
    try {
      const response = await fetch(`${API}/build-cv`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not build the CV')
      setText(data.cv_text)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not build the CV')
    } finally {
      setBuilding(false)
    }
  }

  function download() {
    const href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
    const link = document.createElement('a')
    link.href = href
    link.download = 'jobflow-cv.txt'
    link.click()
    URL.revokeObjectURL(href)
  }

  if (text) return <div className="modal-backdrop"><section className="modal cv-result"><button className="close" onClick={onClose}><X size={18}/></button><p className="eyebrow">YOUR NEW CV</p><h2>Ready to review.</h2><p className="modal-company">Only facts from your answers were used.</p><textarea value={text} readOnly/><div className="modal-actions"><button className="draft-button" onClick={download}><Download size={15}/> Download .txt</button><button className="apply-button" onClick={() => onUse(text)}>Use for job search <ArrowUpRight size={16}/></button></div><small>Review the CV before using it. You can edit the downloaded text anytime.</small></section></div>

  return <div className="modal-backdrop"><section className="modal cv-builder"><button className="close" onClick={onClose}><X size={18}/></button><p className="eyebrow">CV BUILDER · {current.label}</p><h2>{current.question}</h2><p className="modal-company">{current.hint}</p><textarea autoFocus value={answers[current.key] ?? ''} onChange={event => setAnswers({ ...answers, [current.key]: event.target.value })} placeholder="Write your answer here…"/><div className="modal-actions"><button className="draft-button" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>Back</button>{step < CV_QUESTIONS.length - 1 ? <button className="apply-button" onClick={() => setStep(step + 1)}>Next <ArrowUpRight size={16}/></button> : <button className="apply-button" onClick={build} disabled={building}>{building ? 'Making your CV...' : 'Make my CV'} <Sparkles size={16}/></button>}</div>{error && <p className="error">{error}</p>}<small>Your answers are only used to create your CV. Nothing is sent to a job board.</small></section></div>
}

function DraftModal({ draft, onClose }: { draft: { job: Job; text: string }; onClose: () => void }) { return <div className="modal-backdrop"><section className="modal"><button className="close" onClick={onClose}><X size={18}/></button><p className="eyebrow">APPLICATION DRAFT</p><h2>{draft.job.title}</h2><p className="modal-company">{draft.job.company}</p><textarea value={draft.text} readOnly/><div className="modal-actions"><button className="draft-button" onClick={() => navigator.clipboard.writeText(draft.text)}>Copy draft</button><a className="apply-button" href={draft.job.url} target="_blank" rel="noreferrer">Open application <ArrowUpRight size={16}/></a></div><small>Review and personalise this before submitting. This app never sends an application automatically.</small></section></div> }

export default App
