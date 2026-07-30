import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import {
  ArrowUpRight, BriefcaseBusiness, CheckCircle2, Download, FileText, MapPin,
  Play, RefreshCw, Search, Send, Settings, Sparkles, UploadCloud, X,
} from 'lucide-react'

type Job = {
  id: string; title: string; company: string; location: string; description: string
  url: string; source: string; opportunity_type: string; score: number
  score_breakdown: Record<string, number>; match_reasons: string[]; keywords: string[]
  status: 'ready' | 'review'; rule_reasons: string[]; direct_listing: boolean
  candidate?: string; profile?: Record<string, unknown>; document_id?: string
}
type SearchData = {
  profile: Record<string, unknown>; document_id: string; queries: string[]
  discovered: number; matched: number; qualified: number; review: number; excluded: number; jobs: Job[]
}
type BatchResult = { candidate: string; error: string | null; data: SearchData | null }
type GeneratedCV = { text: string; documentId: string; pdfUrl: string }
type SavedCV = { documentId: string; sourceName: string }
type TailoredCV = { document_id: string; pdf_url: string; filename: string; cached: boolean }
type ModelSettings = {
  provider: 'ollama_local' | 'ollama_cloud'; base_url: string; model: string; api_key_configured: boolean
}
type OllamaModel = { name: string; size: number; parameter_size: string; quantization: string }
type ApplicationSession = {
  id: string; status: string; message: string
  details: { filled_fields?: string[]; missing_required?: string[]; blockers?: string[]; unavailable?: string[]; cv_uploaded?: boolean }
}

const API = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000/api' : '/api')
const API_ORIGIN = API.replace(/\/api\/?$/, '')
const CV_QUESTIONS = [
  { key: 'identity', label: '1 / 6', question: 'What is your name, email, phone, city, and LinkedIn/GitHub link?', hint: 'A full name and at least one email or phone number are required.' },
  { key: 'goal', label: '2 / 6', question: 'What role or internship are you targeting, and are you currently a student?', hint: 'Include your current career stage so internships and graduate roles can be prioritised.' },
  { key: 'experience', label: '3 / 6', question: 'Tell me about work, freelance experience, volunteering, or internships.', hint: 'This can be empty if you have strong projects and education.' },
  { key: 'projects', label: '4 / 6', question: 'What are your best technical or non-technical projects?', hint: 'State the problem, what you did, tools used, and the factual result.' },
  { key: 'skills', label: '5 / 6', question: 'Which skills and tools can you genuinely use?', hint: 'Add at least three comma-separated skills.' },
  { key: 'education', label: '6 / 6', question: 'What education, graduation date, certificates, languages, or achievements should be included?', hint: 'Current education matters, especially when you are a student.' },
] as const

function App() {
  const [location, setLocation] = useState('Cairo')
  const [limit, setLimit] = useState(10)
  const [liveBrowser, setLiveBrowser] = useState(false)
  const [targetRoles, setTargetRoles] = useState('AI Engineer, LLM Engineer, Software Engineer')
  const [excludedTitleTerms, setExcludedTitleTerms] = useState('')
  const [singleFile, setSingleFile] = useState<File | null>(null)
  const [generatedCV, setGeneratedCV] = useState<GeneratedCV | null>(null)
  const [savedCV, setSavedCV] = useState<SavedCV | null>(null)
  const [cvBuilderOpen, setCvBuilderOpen] = useState(false)
  const [single, setSingle] = useState<SearchData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [captchaBlocked, setCaptchaBlocked] = useState(false)
  const [notice, setNotice] = useState('')
  const [draft, setDraft] = useState<{ job: Job; text: string } | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [modelLabel, setModelLabel] = useState('Ollama not configured')
  const [application, setApplication] = useState<ApplicationSession | null>(null)
  const [applicationJobId, setApplicationJobId] = useState<string | null>(null)
  const [applicationAnswers, setApplicationAnswers] = useState<Record<string, string>>(() => {
    try { return JSON.parse(localStorage.getItem('jobflow-application-answers') || '{}') }
    catch { return {} }
  })

  useEffect(() => {
    fetch(`${API}/model-settings`).then(response => response.json()).then(data => {
      setModelLabel(data.model ? `${data.model} · ${data.provider === 'ollama_local' ? 'local' : 'cloud'}` : 'Choose an Ollama model')
    }).catch(() => setModelLabel('Backend offline'))
    fetch(`${API}/documents/active`).then(response => response.json()).then(data => {
      if (data.document) {
        setSavedCV({ documentId: data.document.document_id, sourceName: data.document.source_name })
      }
    }).catch(() => { /* Upload remains available when no reusable document exists. */ })
  }, [])

  const jobs = useMemo(
    () => single?.jobs.map(job => ({ ...job, profile: single.profile, document_id: single.document_id })) ?? [],
    [single],
  )

  async function runSearch(forceBackground = false) {
    setError(''); setCaptchaBlocked(false); setNotice(''); setLoading(true)
    try {
      const form = new FormData()
      form.append('location', location)
      form.append('limit', String(limit))
      form.append('live_browser', String(forceBackground ? false : liveBrowser))
      form.append('target_roles', targetRoles)
      form.append('excluded_title_terms', excludedTitleTerms)
      if (singleFile) form.append('cv', singleFile)
      else if (generatedCV) form.append('cv_document_id', generatedCV.documentId)
      else if (savedCV) form.append('cv_document_id', savedCV.documentId)
      else throw new Error('Upload a CV or create an ATS CV first.')
      form.append('user_id', `web-${generatedCV?.documentId || singleFile?.name || 'profile'}`)
      const response = await fetch(`${API}/search`, { method: 'POST', body: form })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.message || 'Search failed')
      setSingle(data)
      setSavedCV({
        documentId: data.document_id,
        sourceName: singleFile?.name || savedCV?.sourceName || 'Generated ATS CV',
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      setError(message)
      setCaptchaBlocked(message.toLowerCase().includes('verification') || message.toLowerCase().includes('captcha'))
    } finally {
      setLoading(false)
    }
  }

  async function prepareApplication(job: Job) {
    setError('')
    const response = await fetch(`${API}/application-draft`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: job.title, company: job.company, keywords: job.keywords, profile: job.profile ?? {} }),
    })
    const data = await response.json()
    if (!response.ok) { setError(data.detail || 'Could not prepare application'); return }
    setDraft({ job, text: data.message })
  }

  async function startApplication(job: Job, autoSubmit: boolean) {
    setError(''); setNotice('')
    if (!job.direct_listing) { window.open(job.url, '_blank', 'noopener,noreferrer'); return }
    if (!job.document_id) { setError('This result does not have a reusable CV PDF. Run a single-CV search again.'); return }
    if (autoSubmit && !window.confirm('Jobflow will fill and submit this application when every required field is complete. Continue?')) return
    const response = await fetch(`${API}/application-sessions`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: job.url,
        document_id: job.document_id,
        profile: { ...(job.profile ?? {}), application_answers: applicationAnswers },
        auto_submit: autoSubmit,
      }),
    })
    const data = await response.json()
    if (!response.ok) { setError(data.detail || 'Could not start application automation'); return }
    setApplication(data)
    setApplicationJobId(job.id)
    setNotice('A visible application browser is running. Jobflow will report exactly what it could fill.')
  }

  function fileChosen(event: ChangeEvent<HTMLInputElement>) {
    setSingleFile(event.target.files?.[0] ?? null)
    if (event.target.files?.[0]) setGeneratedCV(null)
  }

  return <main>
    <aside className="sidebar">
      <div className="brand"><div className="brandmark"><Sparkles size={18}/></div><span>jobflow</span></div>
      <div className="nav-title">WORKSPACE</div>
      <button className="nav-active"><Search size={17}/> Discover jobs</button>
      <button className="nav" onClick={() => setSettingsOpen(true)}><Settings size={17}/> Model settings</button>
      <div className="side-bottom"><div className="model-dot"/>{modelLabel}</div>
    </aside>

    <section className="content">
      <header><div><p className="eyebrow">JOB DISCOVERY SYSTEM</p><h1>Find the right work,<br/><em>without the busywork.</em></h1></div><div className="header-status"><CheckCircle2 size={16}/> Local-first</div></header>
      <section className="control-panel">
        <div className="mode-switch personal-flow"><span className="single-cv-label"><FileText size={17}/> Your CV</span><button className="no-cv-button" onClick={() => setCvBuilderOpen(true)}><Sparkles size={17}/> I don't have a CV - build an ATS PDF</button></div>
        {generatedCV && <p className="generated-ready"><CheckCircle2 size={14}/> ATS PDF generated and selected. <a href={`${API_ORIGIN}${generatedCV.pdfUrl}`} target="_blank" rel="noreferrer">Open PDF</a></p>}
        <div className="setup-grid">
          <label className="upload-zone"><input type="file" accept=".pdf,.txt" onChange={fileChosen}/><UploadCloud size={23}/><span>{singleFile?.name ?? (generatedCV ? 'Generated ATS CV selected' : savedCV ? `${savedCV.sourceName} · saved` : 'Drop a CV here or browse')}</span><small>{savedCV && !singleFile && !generatedCV ? 'Reused automatically after refresh · choose a file to replace it' : 'PDF or TXT · kept locally and reused for applications'}</small></label>
          <label className="field"><span>Target location</span><div><MapPin size={16}/><input value={location} onChange={event => setLocation(event.target.value)} placeholder="Cairo or Remote"/></div></label>
          <label className="field short"><span>Jobs to show</span><select value={limit} onChange={event => setLimit(Number(event.target.value))}>{[3, 5, 10].map(value => <option key={value}>{value}</option>)}</select></label>
          <label className="field role-field"><span>Target roles</span><input value={targetRoles} onChange={event => setTargetRoles(event.target.value)} placeholder="AI Engineer, Data Analyst"/></label>
          <label className="field exclude-field"><span>Exclude titles</span><input value={excludedTitleTerms} onChange={event => setExcludedTitleTerms(event.target.value)} placeholder="Sales, Senior"/></label>
          <label className="watch-toggle"><input type="checkbox" checked={liveBrowser} onChange={event => setLiveBrowser(event.target.checked)}/><span>Watch discovery live</span><small>One visible Playwright session is reused for every search query.</small></label>
          <button className="search-button" onClick={() => runSearch()} disabled={loading}><Play size={17} fill="currentColor"/>{loading ? 'Discovering and ranking...' : 'Find matching opportunities'}</button>
        </div>
        {error && <p className="error">{error}</p>}
        {captchaBlocked && <button className="captcha-retry" onClick={() => runSearch(true)} disabled={loading}>Retry in background mode</button>}
        {notice && <p className="notice">{notice}</p>}
      </section>

      <section className={`pipeline ${loading ? 'running' : ''}`}><span className="pipeline-label">APPLICATION PIPELINE</span><div className="pipeline-steps"><b>1. Discover</b><i/><b>2. Match</b><i/><b>3. Student fit</b><i/><b>4. Rank</b><i/><b>5. Fill</b><i/><b>6. Submit</b></div><p>{loading ? 'Ollama and Playwright are working now.' : 'Student status, opportunity type, skills, and seniority all affect ranking.'}</p></section>
      {jobs.length > 0 && <><section className="results-top"><div><p className="eyebrow">QUALIFIED OPPORTUNITIES</p><h2>{jobs.length} roles ready to review</h2><p>{single?.profile.is_student ? 'Student profile detected: internships and graduate roles receive priority.' : 'Ranked by semantic fit and career stage.'}</p></div><div className="metrics"><Metric label="DISCOVERED" value={single?.discovered ?? 0}/><Metric label="MATCHED" value={single?.matched ?? 0}/><Metric label="QUALIFIED" value={single?.qualified ?? 0}/><Metric label="TOP SCORE" value={Math.round(Math.max(...jobs.map(job => job.score)) * 100)}/></div></section><Scoreboard jobs={jobs}/><section className="job-grid">{jobs.map((job, index) => <JobCard job={job} key={job.id} index={index} onPrepare={prepareApplication} onApply={startApplication}/>)}</section></>}
      {!jobs.length && !loading && <section className="empty"><BriefcaseBusiness size={30}/><h2>{single ? 'No open matching opportunities found.' : savedCV ? 'Your saved CV is ready.' : 'Your job board will appear here.'}</h2><p>{single ? (single.discovered > 0 ? `${single.excluded} stale, closed, or unsuitable result(s) were removed. Try broader roles or a different location.` : 'No recent results were returned. Try broader roles or a different location.') : savedCV ? 'Click Find matching opportunities; you do not need to upload the CV again.' : 'Add a CV, choose a local or cloud Ollama model, then start discovery.'}</p></section>}
    </section>
    {draft && <DraftModal draft={draft} onClose={() => setDraft(null)}/>}
    {cvBuilderOpen && <CVBuilder onClose={() => setCvBuilderOpen(false)} onUse={cv => { setGeneratedCV(cv); setSavedCV({ documentId: cv.documentId, sourceName: 'Generated ATS CV' }); setSingleFile(null); setCvBuilderOpen(false) }}/>}
    {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} onSaved={settings => { setModelLabel(`${settings.model} · ${settings.provider === 'ollama_local' ? 'local' : 'cloud'}`); setSettingsOpen(false) }}/>}
    {application && <ApplicationModal initial={application} onClose={() => { setApplication(null); setApplicationJobId(null) }} onUnavailable={() => {
      if (!applicationJobId) return
      setSingle(current => current ? {
        ...current,
        jobs: current.jobs.filter(job => job.id !== applicationJobId),
        excluded: current.excluded + 1,
        qualified: Math.max(0, current.qualified - 1),
      } : current)
    }} onAnswersSaved={values => {
      const updated = { ...applicationAnswers, ...values }
      setApplicationAnswers(updated)
      localStorage.setItem('jobflow-application-answers', JSON.stringify(updated))
    }}/>}
  </main>
}

function Metric({ label, value }: { label: string; value: number }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div> }

function Scoreboard({ jobs }: { jobs: Job[] }) {
  const ranked = [...jobs].sort((a, b) => b.score - a.score).slice(0, 5)
  return <section className="scoreboard"><div><p className="eyebrow">SEMANTIC + CAREER-STAGE SCORE</p><h3>Why these opportunities rank higher</h3><p>The score combines model meaning, verified skill overlap, target role, student fit, and seniority.</p></div><div className="score-list">{ranked.map(job => { const percent = Math.round(job.score * 100); return <div className="score-row" key={job.id}><div className="score-title"><span>{job.title}</span><b>{percent}%</b></div><div className="score-track"><i style={{ width: `${percent}%` }}/></div><small>{job.opportunity_type.toUpperCase()} · {job.match_reasons[0] || `${job.keywords.length} verified skill matches`}</small></div> })}</div></section>
}

function JobCard({ job, index, onPrepare, onApply }: { job: Job; index: number; onPrepare: (job: Job) => void; onApply: (job: Job, autoSubmit: boolean) => void }) {
  const [tailoredCV, setTailoredCV] = useState<TailoredCV | null>(null)
  const [cvBusy, setCvBusy] = useState(false)
  const [cvError, setCvError] = useState('')

  async function ensureTailoredCV(): Promise<TailoredCV> {
    if (tailoredCV) return tailoredCV
    if (!job.document_id) throw new Error('Run the search with a reusable CV first.')
    setCvBusy(true); setCvError('')
    try {
      const response = await fetch(`${API}/tailored-cv`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_id: job.document_id,
          title: job.title,
          company: job.company,
          description: job.description,
          url: job.url,
          keywords: job.keywords,
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not tailor the CV.')
      setTailoredCV(data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not tailor the CV.'
      setCvError(message)
      throw err
    } finally {
      setCvBusy(false)
    }
  }

  async function downloadTailoredCV() {
    try {
      const tailored = await ensureTailoredCV()
      const response = await fetch(`${API_ORIGIN}${tailored.pdf_url}`)
      if (!response.ok) throw new Error('Could not download the tailored PDF.')
      const blobUrl = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = blobUrl
      link.download = tailored.filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
    } catch (err) {
      setCvError(err instanceof Error ? err.message : 'Could not download the tailored PDF.')
    }
  }

  async function applyWithTailoredCV(autoSubmit: boolean) {
    try {
      const tailored = await ensureTailoredCV()
      onApply({ ...job, document_id: tailored.document_id }, autoSubmit)
    } catch { /* The card already shows the generation error. */ }
  }

  return <article className="job-card" style={{ animationDelay: `${Math.min(index, 8) * 55}ms` }}><div className="job-meta"><span className={`source ${job.direct_listing ? 'direct' : ''}`}>{job.opportunity_type.toUpperCase()}</span><span className={`status ${job.status}`}>{job.status === 'ready' ? 'READY' : 'REVIEW'}</span></div><h3>{job.title}</h3><p className="company">{job.company} <span>·</span> {job.location}</p><p className="description">{job.description || 'Open the listing to learn more.'}</p><div className="keywords">{job.keywords.map(keyword => <span key={keyword}>{keyword}</span>)}</div><p className="rule-reason">{job.match_reasons[0] || job.rule_reasons[0]}</p>{cvError && <p className="cv-card-error">{cvError}</p>}<div className="card-actions stacked"><button className="draft-button" onClick={() => onPrepare(job)}>Draft note</button><button className="apply-button" disabled={cvBusy} onClick={() => applyWithTailoredCV(false)}>{cvBusy ? 'Tailoring CV...' : 'Autofill & review'} <ArrowUpRight size={15}/></button><button className="tailored-cv-button" disabled={cvBusy} onClick={downloadTailoredCV}><Download size={14}/>{cvBusy ? 'Building ATS PDF...' : tailoredCV ? 'Download tailored CV' : 'Download CV'}</button>{job.status === 'ready' && job.direct_listing && <button className="auto-submit-button" disabled={cvBusy} onClick={() => applyWithTailoredCV(true)}><Send size={14}/> Auto apply with tailored CV</button>}</div></article>
}

function CVBuilder({ onClose, onUse }: { onClose: () => void; onUse: (cv: GeneratedCV) => void }) {
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [result, setResult] = useState<GeneratedCV | null>(null)
  const [building, setBuilding] = useState(false)
  const [error, setError] = useState('')
  const [readiness, setReadiness] = useState<{ progress: number; missing: { field: string; message: string }[] }>({ progress: 0, missing: [] })
  const current = CV_QUESTIONS[step]

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API}/cv/readiness`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers }) })
        if (response.ok) setReadiness(await response.json())
      } catch { /* The final generation request remains authoritative. */ }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [answers])

  async function build() {
    setBuilding(true); setError('')
    try {
      const response = await fetch(`${API}/build-cv`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers }) })
      const data = await response.json()
      if (!response.ok) {
        if (data.detail?.readiness) setReadiness(data.detail.readiness)
        throw new Error(data.detail?.message || data.detail || 'Could not build the CV')
      }
      setResult({ text: data.cv_text, documentId: data.document_id, pdfUrl: data.pdf_url })
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not build the CV') }
    finally { setBuilding(false) }
  }

  if (result) return <div className="modal-backdrop"><section className="modal cv-result"><button className="close" onClick={onClose}><X size={18}/></button><p className="eyebrow">ATS PDF READY</p><h2>Your CV is ready to review.</h2><p className="modal-company">Only facts from your answers were used.</p><textarea value={result.text} readOnly/><div className="modal-actions"><a className="draft-button" href={`${API_ORIGIN}${result.pdfUrl}`} download><Download size={15}/> Download PDF</a><button className="apply-button" onClick={() => onUse(result)}>Use for search <ArrowUpRight size={16}/></button></div></section></div>

  return <div className="modal-backdrop"><section className="modal cv-builder"><button className="close" onClick={onClose}><X size={18}/></button><div className="readiness"><span style={{ width: `${readiness.progress}%` }}/></div><p className="eyebrow">CV BUILDER · {current.label} · {readiness.progress}% VERIFIED</p><h2>{current.question}</h2><p className="modal-company">{current.hint}</p><textarea autoFocus value={answers[current.key] ?? ''} onChange={event => setAnswers({ ...answers, [current.key]: event.target.value })} placeholder="Write factual information here..."/><div className="modal-actions"><button className="draft-button" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>Back</button>{step < CV_QUESTIONS.length - 1 ? <button className="apply-button" onClick={() => setStep(step + 1)}>Next <ArrowUpRight size={16}/></button> : <button className="apply-button" onClick={build} disabled={building || readiness.progress < 100}>{building ? 'Building ATS PDF...' : 'Generate ATS PDF'} <Sparkles size={16}/></button>}</div>{readiness.missing.length > 0 && step === CV_QUESTIONS.length - 1 && <ul className="missing-list">{readiness.missing.map(item => <li key={item.field}>{item.message}</li>)}</ul>}{error && <p className="error">{error}</p>}</section></div>
}

function SettingsModal({ onClose, onSaved }: { onClose: () => void; onSaved: (settings: ModelSettings) => void }) {
  const [settings, setSettings] = useState<ModelSettings>({ provider: 'ollama_local', base_url: 'http://127.0.0.1:11434', model: '', api_key_configured: false })
  const [apiKey, setApiKey] = useState('')
  const [models, setModels] = useState<OllamaModel[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { fetch(`${API}/model-settings`).then(r => r.json()).then(setSettings).catch(() => setError('Could not load model settings.')) }, [])

  function switchProvider(provider: 'ollama_local' | 'ollama_cloud') {
    setSettings({ ...settings, provider, base_url: provider === 'ollama_local' ? 'http://127.0.0.1:11434' : 'https://ollama.com', model: '' })
    setModels([])
  }
  async function refresh() {
    setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/model-settings/models`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: settings.provider, base_url: settings.base_url, api_key: apiKey || undefined }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not list models')
      setModels(data.models)
      if (!settings.model && data.models.length) setSettings({ ...settings, model: data.models[0].name })
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not list models') }
    finally { setBusy(false) }
  }
  async function save() {
    setBusy(true); setError('')
    try {
      const response = await fetch(`${API}/model-settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...settings, api_key: apiKey || undefined }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not save settings')
      onSaved(data)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save settings') }
    finally { setBusy(false) }
  }
  return <div className="modal-backdrop"><section className="modal settings-modal"><button className="close" onClick={onClose}><X size={18}/></button><p className="eyebrow">OLLAMA MODEL SETTINGS</p><h2>Choose local or cloud inference.</h2><div className="provider-tabs"><button className={settings.provider === 'ollama_local' ? 'selected' : ''} onClick={() => switchProvider('ollama_local')}>Local</button><button className={settings.provider === 'ollama_cloud' ? 'selected' : ''} onClick={() => switchProvider('ollama_cloud')}>Cloud</button></div><label className="modal-field"><span>Base URL</span><input value={settings.base_url} onChange={event => setSettings({ ...settings, base_url: event.target.value })}/></label>{settings.provider === 'ollama_cloud' && <label className="modal-field"><span>API key {settings.api_key_configured && '(already configured)'}</span><input type="password" value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder={settings.api_key_configured ? 'Leave blank to keep current key' : 'Required for Ollama Cloud'}/></label>}<div className="model-picker"><button className="draft-button" onClick={refresh} disabled={busy}><RefreshCw size={14}/>{busy ? 'Refreshing...' : 'Refresh models'}</button><select value={settings.model} onChange={event => setSettings({ ...settings, model: event.target.value })}><option value="">Choose a model</option>{models.map(model => <option value={model.name} key={model.name}>{model.name}{model.parameter_size ? ` · ${model.parameter_size}` : ''}</option>)}{settings.model && !models.some(model => model.name === settings.model) && <option value={settings.model}>{settings.model}</option>}</select></div>{error && <p className="error">{error}</p>}<button className="apply-button save-settings" onClick={save} disabled={busy || !settings.model}>Save model</button><small>Local Ollama needs no API key. Cloud keys stay in backend memory and are not written to the settings file.</small></section></div>
}

function ApplicationModal({ initial, onClose, onUnavailable, onAnswersSaved }: { initial: ApplicationSession; onClose: () => void; onUnavailable: () => void; onAnswersSaved: (values: Record<string, string>) => void }) {
  const [session, setSession] = useState(initial)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  useEffect(() => {
    if (['submitted', 'closed', 'failed', 'expired', 'unavailable'].includes(session.status)) return
    const timer = window.setInterval(async () => {
      const response = await fetch(`${API}/application-sessions/${session.id}`)
      if (response.ok) setSession(await response.json())
    }, 1200)
    return () => window.clearInterval(timer)
  }, [session.id, session.status])
  useEffect(() => {
    if (session.status === 'unavailable') onUnavailable()
  }, [session.status])
  async function command(value: 'submit' | 'retry' | 'close', values: Record<string, string> = {}) {
    const response = await fetch(`${API}/application-sessions/${session.id}/commands`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: value, values }) })
    if (response.ok) setSession(await response.json())
    if (value === 'close') onClose()
  }
  function saveAndRetry() {
    const values = Object.fromEntries(Object.entries(answers).filter(([, value]) => value.trim()))
    onAnswersSaved(values)
    command('retry', values)
  }
  return <div className="modal-backdrop"><section className="modal application-modal"><button className="close" onClick={() => command('close')}><X size={18}/></button><p className="eyebrow">APPLICATION AUTOMATION · {session.status.replaceAll('_', ' ').toUpperCase()}</p><h2>{session.message}</h2><p className="modal-company">{session.details.cv_uploaded ? 'CV PDF uploaded. ' : ''}{session.details.filled_fields?.length || 0} fields filled.</p>{session.details.blockers?.map(item => <p className="error" key={item}>{item}</p>)}{session.details.unavailable?.map(item => <p className="error" key={item}>{item}</p>)}{session.details.missing_required?.length ? <div className="answer-fields"><h3>Required input still missing</h3>{session.details.missing_required.map(item => <label className="modal-field" key={item}><span>{item}</span><input value={answers[item] ?? ''} onChange={event => setAnswers({ ...answers, [item]: event.target.value })} placeholder="Add a factual answer"/></label>)}</div> : null}<div className="modal-actions">{session.status === 'ready_to_submit' && <button className="auto-submit-button" onClick={() => command('submit')}><Send size={14}/> Confirm submit</button>}{session.status === 'needs_input' && <button className="auto-submit-button" onClick={saveAndRetry}><RefreshCw size={14}/> Save answers & retry</button>}{['blocked', 'needs_review'].includes(session.status) && <button className="auto-submit-button" onClick={() => command('retry')}><RefreshCw size={14}/> I signed in - retry</button>}<button className="draft-button" onClick={() => command('close')}>Close browser</button></div><small>For LinkedIn, use the direct email/password form once; Google blocks automated browser sign-in. The local profile reuses your LinkedIn session afterward.</small></section></div>
}

function DraftModal({ draft, onClose }: { draft: { job: Job; text: string }; onClose: () => void }) { return <div className="modal-backdrop"><section className="modal"><button className="close" onClick={onClose}><X size={18}/></button><p className="eyebrow">APPLICATION DRAFT</p><h2>{draft.job.title}</h2><p className="modal-company">{draft.job.company}</p><textarea value={draft.text} readOnly/><div className="modal-actions"><button className="draft-button" onClick={() => navigator.clipboard.writeText(draft.text)}>Copy draft</button><button className="apply-button" onClick={() => window.open(draft.job.url, '_blank', 'noopener,noreferrer')}>Open listing <ArrowUpRight size={16}/></button></div></section></div> }

export default App
