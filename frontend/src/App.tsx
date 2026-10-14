import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertTriangle, ArrowUpRight, BarChart3, Bell, Bookmark, BookmarkCheck, Bot, BriefcaseBusiness, Building2, Check, CheckCircle2,
  ChevronDown, ChevronRight, ChevronUp, Compass, Copy, Download, ExternalLink, FileText,
  CircleDollarSign, GraduationCap, Home, LayoutList, Mail, MapPin, Menu, MessageSquare,
  MoreHorizontal, RefreshCw, Search, Send, Settings, SlidersHorizontal, Sparkles, Target, UploadCloud,
  ShieldCheck, UserRound, UserRoundSearch, X,
} from 'lucide-react'
import { ApplicationsPage, InterviewsPage, OffersPage, ProfileDataPrompt, ProfilePage, TodayPage } from './EmploymentPages'
import { CareerDevelopmentHub, QualificationPlanPage, ReadinessPage, SkillProofPage } from './DevelopmentPages'
import { AuthPage } from './AuthPages'
import { SettingsPage } from './SettingsPage'
import { BrandLogo, UserAvatar } from './ui'
import { useI18n } from './i18n'

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
  search_location?: string; target_roles?: string
}
type SearchProgressEvent = {
  id: string; stage: string; status: 'active' | 'done' | 'error'
  title: string; detail: string
  meta: {
    sources?: { key: string; label: string; count: number }[]
    found?: number; matched?: number; remaining?: number; query_count?: number
  }
}
type SearchProgressJob = {
  id: string; status: 'queued' | 'running' | 'completed' | 'failed'
  stage: string; progress: number; headline: string; detail: string
  events: SearchProgressEvent[]; result?: SearchData | null; error?: string | null
}
type BatchResult = { candidate: string; error: string | null; data: SearchData | null }
type GeneratedCV = { text: string; documentId: string; pdfUrl: string }
type SavedCV = { documentId: string; sourceName: string }
type CVInsight = {
  id: string; label: string; value: string | string[]; basis: 'explicit' | 'derived' | 'user_claim'
  confidence: number; evidence_quotes: string[]; explanation: string; review_state: string; user_evidence?: string[]
}
type CVInsightReview = {
  document_id: string; summary: string; insights: CVInsight[]; language: 'en' | 'ar'
  review_status: 'pending' | 'approved'; generated_by: 'llm'; source_note: string
  recommendation: { path: 'internship' | 'job' | 'either'; level: string; role_titles: string[]; reason: string; confidence: number; basis: 'derived' }
}
type TailoredCV = { document_id: string; pdf_url: string; filename: string; cached: boolean }
type ModelSettings = {
  provider: 'ollama_local' | 'ollama_cloud'; base_url: string; model: string; api_key_configured: boolean
}
type OllamaModel = { name: string; size: number; parameter_size: string; quantization: string }
type MissingApplicationField = {
  field_id: string; memory_key: string; label: string; question: string
  options: string[]; input_type: string
}
type ApplicationSession = {
  id: string; status: string; message: string; application_id?: string | null; recoverable?: boolean
  details: {
    filled_fields?: string[]; missing_required?: MissingApplicationField[]; blockers?: string[]
    unavailable?: string[]; cv_uploaded?: boolean; reused_answers?: string[]
    answer_memory_count?: number; login_session_persistent?: boolean
  }
}
type JobBrief = {
  summary: string; responsibilities: string[]; requirements: string[]
  facts: {
    location: string; employment_type: string; work_mode: string; salary: string
    schedule: string; duration: string; experience: string; posted: string; deadline: string
  }
  company: { name: string; url: string; industry: string; employees: string; founded: string }
  listing_url: string; missing: string[]; quality: 'full' | 'partial' | 'limited'
  generated: boolean; company_snapshot: string; source_note: string
  listing_signals: { trait: string; evidence_quote: string }[]
}
type CareerQuestion = {
  memory_key: string; kind: string; subject: string; question: string; reason: string
  options: string[]; input_type: 'choice' | 'url' | 'text'; placeholder?: string
  cv_safe: boolean; cv_section: string
}
type CareerDecision = {
  id: string; kind: string; prompt: string; reason: string; job_ids: string[]; locations?: string[]
  options: { value: string; label: string; impact_jobs: number }[]
}
type AcceptancePlan = {
  message: string; generated: boolean
  activities: { state: 'done' | 'active'; label: string }[]
  recommendations: {
    id: string; kind: string; priority: string; title: string; detail: string
    impact_jobs: number; evidence: { job_id: string; job_title: string; quote: string }[]; action_label: string
  }[]
  question: CareerQuestion | null; decision: CareerDecision | null
  exposure: { suggested: boolean; reason: string }
  remembered: Record<string, string>; source_note: string
}
type CareerCVUpdate = { document_id: string; pdf_url: string; filename: string; added: Record<string, string[]> }
type GrowthResearch = {
  query: string; search_url: string; message: string
  items: { title: string; url: string; snippet: string; type: string; verification: string }[]
}
type OutreachLead = {
  id: string; name: string; role: string; channel: 'email' | 'linkedin'; destination: string
  url: string; source: string; verified: boolean
}
type OutreachContext = { job: Job; companyUrl: string }
type InstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> }
type WorkspaceMode = 'today' | 'career' | 'readiness' | 'development' | 'proof' | 'opportunities' | 'growth' | 'applications' | 'interviews' | 'offers' | 'profile' | 'settings'
type Identity = { name: string; email: string; avatarUrl?: string }
type WorkspaceNotification = { id: string; title: string; detail: string; target: WorkspaceMode }

const API = import.meta.env.VITE_API_URL || '/api'
const API_ORIGIN = API.replace(/\/api\/?$/, '')
const CV_QUESTIONS = [
  { key: 'identity', label: '1 / 6', question: 'What is your name, email, phone, city, and LinkedIn/GitHub link?', hint: 'A full name and at least one email or phone number are required.' },
  { key: 'goal', label: '2 / 6', question: 'What role or internship are you targeting, and are you currently a student?', hint: 'Include your current career stage so internships and graduate roles can be prioritised.' },
  { key: 'experience', label: '3 / 6', question: 'Tell me about work, freelance experience, volunteering, or internships.', hint: 'This can be empty if you have strong projects and education.' },
  { key: 'projects', label: '4 / 6', question: 'What are your best technical or non-technical projects?', hint: 'State the problem, what you did, tools used, and the factual result.' },
  { key: 'skills', label: '5 / 6', question: 'Which skills and tools can you genuinely use?', hint: 'Add at least three comma-separated skills.' },
  { key: 'education', label: '6 / 6', question: 'What education, graduation date, certificates, languages, or achievements should be included?', hint: 'Current education matters, especially when you are a student.' },
] as const

function SearchActivity({ progress }: { progress: SearchProgressJob }) {
  const sourceEvent = [...progress.events].reverse().find(event => event.meta.sources?.length)
  const sources = sourceEvent?.meta.sources || []
  return <section className="search-progress" aria-live="polite" aria-busy={progress.status !== 'completed'}>
    <header className="progress-heading">
      <span className="progress-agent"><Bot size={20}/></span>
      <div>
        <span className="progress-live"><i/> Live search activity</span>
        <strong>{progress.headline}</strong>
        <p>{progress.detail}</p>
      </div>
      <b className="progress-percent">{Math.max(1, progress.progress)}%</b>
    </header>

    <div className="progress-track" aria-label={`${progress.progress}% complete`}><i style={{ width: `${progress.progress}%` }}/></div>

    <div className="progress-content">
      <ol className="search-timeline">
        {progress.events.map(event => <li className={event.status} key={event.id}>
          <span className="timeline-marker">{event.status === 'done' ? <Check size={14}/> : event.status === 'error' ? <AlertTriangle size={14}/> : <RefreshCw className="spin" size={13}/>}</span>
          <div><b>{event.title}</b><p>{event.detail}</p></div>
        </li>)}
      </ol>

      <aside className="progress-context" aria-label="Search evidence and CV safety">
        <div className="progress-context-heading"><Sparkles size={17}/><b>What I know so far</b></div>
        {sources.length > 0 ? <div className="source-evidence">
          {sources.map(source => <span key={source.key}><b>{source.count}</b>{source.label}</span>)}
        </div> : <p>Source counts will appear here as soon as each live search returns. Nothing is estimated.</p>}
        <div className="cv-safety"><CheckCircle2 size={17}/><p><b>Your CV stays factual.</b><span>I can recommend stronger wording and tailoring, but I won’t add skills, results, or experience you didn’t provide.</span></p></div>
      </aside>
    </div>
  </section>
}

function App() {
  const { locale, setLocale, t } = useI18n()
  const browserLocation = useLocation()
  const navigate = useNavigate()
  const [location, setLocation] = useState(() => localStorage.getItem('wazzefni-target-location') || localStorage.getItem('jobflow-target-location') || 'Cairo')
  const [limit, setLimit] = useState(10)
  const [liveBrowser, setLiveBrowser] = useState(false)
  const [targetRoles, setTargetRoles] = useState('')
  const [excludedTitleTerms, setExcludedTitleTerms] = useState('')
  const [singleFile, setSingleFile] = useState<File | null>(null)
  const [generatedCV, setGeneratedCV] = useState<GeneratedCV | null>(null)
  const [savedCV, setSavedCV] = useState<SavedCV | null>(null)
  const [cvReview, setCvReview] = useState<CVInsightReview | null>(null)
  const [cvReviewOpen, setCvReviewOpen] = useState(false)
  const [cvAnalyzing, setCvAnalyzing] = useState(false)
  const [cvAnalysisError, setCvAnalysisError] = useState('')
  const [cvBuilderOpen, setCvBuilderOpen] = useState(false)
  const [single, setSingle] = useState<SearchData | null>(null)
  const [loading, setLoading] = useState(false)
  const [searchProgress, setSearchProgress] = useState<SearchProgressJob | null>(null)
  const [error, setError] = useState('')
  const [captchaBlocked, setCaptchaBlocked] = useState(false)
  const [notice, setNotice] = useState('')
  const [draft, setDraft] = useState<{ job: Job; text: string } | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [readNotificationIds, setReadNotificationIds] = useState<string[]>([])
  const notificationsRef = useRef<HTMLDivElement>(null)
  const [installPrompt, setInstallPrompt] = useState<InstallPromptEvent | null>(null)
  const [modelLabel, setModelLabel] = useState('Ollama not configured')
  const [application, setApplication] = useState<ApplicationSession | null>(null)
  const [applicationJobId, setApplicationJobId] = useState<string | null>(null)
  const [identity, setIdentity] = useState<Identity>({ name: '', email: '' })
  const [authState, setAuthState] = useState<'checking' | 'authenticated' | 'anonymous'>('checking')
  const [searchPanelOpen, setSearchPanelOpen] = useState(true)
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(() => {
    const page = browserLocation.pathname.split('/').filter(Boolean)[0]
    return ['today', 'career', 'readiness', 'development', 'proof', 'opportunities', 'growth', 'applications', 'interviews', 'offers', 'profile', 'settings'].includes(page)
      ? page as WorkspaceMode
      : 'today'
  })
  const [preferencesOpen, setPreferencesOpen] = useState(true)
  const [resultFilter, setResultFilter] = useState<'all' | 'ready' | 'improve' | 'unlock' | 'training' | 'saved'>('all')
  const [resultQuery, setResultQuery] = useState('')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [briefs, setBriefs] = useState<Record<string, JobBrief>>({})
  const [briefLoading, setBriefLoading] = useState<Record<string, boolean>>({})
  const [briefErrors, setBriefErrors] = useState<Record<string, string>>({})
  const [careerPlan, setCareerPlan] = useState<AcceptancePlan | null>(null)
  const [careerLoading, setCareerLoading] = useState(false)
  const [careerError, setCareerError] = useState('')
  const [careerAnswerBusy, setCareerAnswerBusy] = useState(false)
  const [careerCV, setCareerCV] = useState<CareerCVUpdate | null>(null)
  const [growthResearch, setGrowthResearch] = useState<GrowthResearch | null>(null)
  const [growthResearchLoading, setGrowthResearchLoading] = useState(false)
  const [outreachContext, setOutreachContext] = useState<OutreachContext | null>(null)
  const [savedJobIds, setSavedJobIds] = useState<string[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('wazzefni-saved-jobs') || localStorage.getItem('jobflow-saved-jobs') || '[]')
      return Array.isArray(saved) ? saved.filter(item => typeof item === 'string') : []
    } catch { return [] }
  })
  const [applicationAnswers, setApplicationAnswers] = useState<Record<string, string>>(() => {
    try { return JSON.parse(localStorage.getItem('wazzefni-application-answers') || localStorage.getItem('jobflow-application-answers') || '{}') }
    catch { return {} }
  })

  useEffect(() => {
    fetch(`${API}/model-settings`).then(response => response.json()).then(data => {
      setModelLabel(data.model ? `${data.model} · ${data.provider === 'ollama_local' ? 'local' : 'cloud'}` : 'Choose an Ollama model')
    }).catch(() => setModelLabel('Backend offline'))
    if (['/login', '/signup', '/forgot-password', '/reset-password'].includes(browserLocation.pathname)) {
      setAuthState('anonymous')
      return
    }
    fetch(`${API}/auth/session`, { credentials: 'include' }).then(response => response.json()).then(data => {
      if (!data.authenticated) { setAuthState('anonymous'); return }
      if (data.locale === 'ar' || data.locale === 'en') setLocale(data.locale)
      setIdentity({ name: data.name || '', email: data.email || '', avatarUrl: data.avatar_url || '' })
      setAuthState('authenticated')
    }).catch(() => setAuthState('anonymous'))
  }, [])

  useEffect(() => {
    if (authState !== 'authenticated') return
    Promise.all([
      fetch(`${API}/documents/active`, { credentials: 'include' }).then(response => response.json()),
      fetch(`${API}/opportunities?limit=100`, { credentials: 'include' }).then(response => response.json()),
      fetch(`${API}/profile`, { credentials: 'include' }).then(response => response.json()),
    ]).then(([documentsData, opportunityData, profileData]) => {
      const active = documentsData.document
      if (active) setSavedCV({ documentId: active.document_id, sourceName: active.source_name })
      const stored = Array.isArray(opportunityData.items) ? opportunityData.items : []
      setSavedJobIds(stored.filter((item: any) => item.status === 'saved').map((item: any) => item.id))
      if (stored.length) {
        const restoredJobs = stored.map((item: any) => ({
          ...(item.payload || {}), id: item.id, title: item.title, company: item.company,
          location: item.location, url: item.url, source: item.source,
          opportunity_type: item.opportunity_type, score: item.match_score,
          direct_listing: item.direct_listing, document_id: active?.document_id,
          description: item.payload?.description || '', keywords: item.payload?.keywords || [],
          match_reasons: item.payload?.match_reasons || [], rule_reasons: item.payload?.rule_reasons || [],
          score_breakdown: item.payload?.score_breakdown || {}, status: item.status === 'ready' ? 'ready' : 'review',
        }))
        setSingle(current => current || {
          profile: { ...(profileData.profile || {}), career_facts: profileData.facts || [] }, document_id: active?.document_id || '', queries: [], jobs: restoredJobs,
          discovered: restoredJobs.length, matched: restoredJobs.length,
          qualified: restoredJobs.filter((item: any) => item.status === 'ready').length,
          review: restoredJobs.filter((item: any) => item.status !== 'ready').length, excluded: 0,
        })
      }
    }).catch(() => { /* Upload and a new search remain available while offline. */ })
    fetch(`${API}/application-sessions`, { credentials: 'include' }).then(response => response.json()).then(data => {
      const recoverable = (data.items || []).find((item: ApplicationSession) => item.status === 'recoverable')
      if (recoverable) {
        setApplication(recoverable)
        setApplicationJobId(recoverable.application_id || null)
      }
    }).catch(() => { /* Recovery is optional when the local API is unavailable. */ })
  }, [authState])

  useEffect(() => {
    const capture = (event: Event) => { event.preventDefault(); setInstallPrompt(event as InstallPromptEvent) }
    const installed = () => setInstallPrompt(null)
    window.addEventListener('beforeinstallprompt', capture)
    window.addEventListener('appinstalled', installed)
    return () => {
      window.removeEventListener('beforeinstallprompt', capture)
      window.removeEventListener('appinstalled', installed)
    }
  }, [])

  useEffect(() => {
    const showCVInsights = (event: Event) => {
      const review = (event as CustomEvent<CVInsightReview>).detail
      if (!review?.document_id) return
      setCvReview(review)
      setCvReviewOpen(true)
    }
    window.addEventListener('wazzefni:cv-insights', showCVInsights)
    return () => window.removeEventListener('wazzefni:cv-insights', showCVInsights)
  }, [])

  useEffect(() => {
    if (!notificationsOpen) return
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!notificationsRef.current?.contains(event.target as Node)) setNotificationsOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNotificationsOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsideClick)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsideClick)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [notificationsOpen])

  async function installApp() {
    if (!installPrompt) return
    await installPrompt.prompt()
    await installPrompt.userChoice
    setInstallPrompt(null)
  }

  useEffect(() => {
    localStorage.setItem('wazzefni-target-location', location)
  }, [location])

  useEffect(() => {
    if (authState !== 'authenticated') return
    if (['/login', '/signup', '/forgot-password', '/reset-password'].includes(browserLocation.pathname)) return
    const expected = `/${workspaceMode}`
    if (browserLocation.pathname !== expected) {
      navigate(expected, { replace: browserLocation.pathname === '/' })
    }
  }, [workspaceMode, browserLocation.pathname, navigate, authState])

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' })
    document.querySelector<HTMLElement>('.content')?.scrollTo({ top: 0, behavior: 'auto' })
  }, [workspaceMode])

  const jobs = useMemo(
    () => single?.jobs.map(job => ({ ...job, profile: single.profile, document_id: single.document_id })) ?? [],
    [single],
  )
  const visibleJobs = useMemo(() => {
      const query = resultQuery.trim().toLowerCase()
    return jobs.filter(job => {
      const isTraining = ['training', 'bootcamp', 'fellowship', 'course'].includes(job.opportunity_type)
      const matchesStatus = resultFilter === 'all'
        || (resultFilter === 'ready' && !isTraining && job.status === 'ready' && job.score >= .8)
        || (resultFilter === 'improve' && !isTraining && job.status === 'ready' && job.score >= .65 && job.score < .8)
        || (resultFilter === 'unlock' && !isTraining && (job.status !== 'ready' || job.score < .65))
        || (resultFilter === 'training' && isTraining)
        || (resultFilter === 'saved' && savedJobIds.includes(job.id))
      const haystack = `${job.title} ${job.company} ${job.location} ${(job.keywords || []).join(' ')}`.toLowerCase()
      return matchesStatus && (!query || haystack.includes(query))
    })
  }, [jobs, resultFilter, resultQuery, savedJobIds])
  const readyCount = useMemo(() => jobs.filter(job => job.status === 'ready').length, [jobs])
  const savedCount = useMemo(() => jobs.filter(job => savedJobIds.includes(job.id)).length, [jobs, savedJobIds])
  const selectedJob = useMemo(
    () => visibleJobs.find(job => job.id === selectedJobId) ?? visibleJobs[0] ?? null,
    [visibleJobs, selectedJobId],
  )
  const notifications = useMemo<WorkspaceNotification[]>(() => {
    if (application?.status !== 'recoverable') return []
    return [{
      id: `recoverable-${application.id}`,
      title: 'Application needs your input',
      detail: application.message || 'Continue the saved application when you are ready.',
      target: 'applications',
    }]
  }, [application])
  const unreadNotificationCount = notifications.filter(item => !readNotificationIds.includes(item.id)).length

  useEffect(() => {
    if (!visibleJobs.length) {
      setSelectedJobId(null)
      return
    }
    if (!selectedJobId || !visibleJobs.some(job => job.id === selectedJobId)) {
      setSelectedJobId(visibleJobs[0].id)
    }
  }, [visibleJobs, selectedJobId])

  useEffect(() => {
    if (selectedJob && !briefs[selectedJob.id] && !briefLoading[selectedJob.id] && !briefErrors[selectedJob.id]) {
      void loadBrief(selectedJob)
    }
  }, [selectedJob?.id, briefs, briefLoading, briefErrors])

  useEffect(() => {
    if (single?.document_id && single.jobs.length) void loadCareerPlan(single)
    else if (!single?.jobs.length) setCareerPlan(null)
  }, [single])

  async function loadCareerPlan(searchData: SearchData) {
    setCareerLoading(true)
    setCareerError('')
    try {
      const response = await fetch(`${API}/career/plan`, {
        credentials: 'include',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_id: searchData.document_id,
          profile: searchData.profile,
          jobs: searchData.jobs,
          location: searchData.search_location || location,
          search: {
            discovered: searchData.discovered,
            matched: searchData.matched,
            qualified: searchData.qualified,
            review: searchData.review,
          },
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not build your acceptance plan.')
      setCareerPlan(data)
    } catch (err) {
      setCareerError(err instanceof Error ? err.message : 'Could not build your acceptance plan.')
    } finally {
      setCareerLoading(false)
    }
  }

  async function saveCareerAnswer(question: CareerQuestion, value: string) {
    if (!single?.document_id || !value.trim()) return false
    setCareerAnswerBusy(true)
    setCareerError('')
    try {
      const response = await fetch(`${API}/career/answers`, {
        credentials: 'include',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_id: single.document_id,
          memory_key: question.memory_key,
          value,
          question: question.question,
          kind: question.kind,
          subject: question.subject,
          cv_safe: question.cv_safe,
          cv_section: question.cv_section,
          update_cv: true,
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not save that answer.')
      const nextDocumentId = data.cv_update?.document_id || single.document_id
      const nextProfile = {
        ...single.profile,
        career_facts: { ...((single.profile.career_facts as Record<string, string>) || {}), [question.memory_key]: value },
      }
      setApplicationAnswers(current => {
        const updated = { ...current, [question.memory_key]: value }
        localStorage.setItem('wazzefni-application-answers', JSON.stringify(updated))
        return updated
      })
      if (data.cv_update) {
        setCareerCV(data.cv_update)
        setSavedCV({ documentId: data.cv_update.document_id, sourceName: data.cv_update.filename })
      }
      setSingle(current => current ? { ...current, document_id: nextDocumentId, profile: nextProfile } : current)
      setCareerPlan(current => current ? {
        ...current,
        question: current.question?.memory_key === question.memory_key ? null : current.question,
        remembered: { ...current.remembered, [question.memory_key]: value },
      } : current)
      setNotice(data.cv_update ? 'Saved. A factual CV update is ready and selected for future applications.' : 'Saved. I will reuse that answer when it matters.')
      return true
    } catch (err) {
      setCareerError(err instanceof Error ? err.message : 'Could not save that answer.')
      return false
    } finally {
      setCareerAnswerBusy(false)
    }
  }

  async function saveCareerDecision(decision: CareerDecision, value: string) {
    const selected = decision.options.find(option => option.value === value)
    if (!selected) return
    const question: CareerQuestion = {
      memory_key: `decision_${decision.id}`,
      kind: 'search_preference',
      subject: decision.kind,
      question: decision.prompt,
      reason: decision.reason,
      options: decision.options.map(option => option.label),
      input_type: 'choice',
      cv_safe: false,
      cv_section: '',
    }
    const saved = await saveCareerAnswer(question, selected.label)
    if (!saved) return
    setCareerPlan(current => current ? { ...current, decision: null } : current)
    if (value === 'include' && decision.locations?.length) {
      setLocation(current => Array.from(new Set([current, ...decision.locations!].filter(Boolean))).join(', '))
      setNotice(`Saved. The next search will include ${decision.locations.join(', ')}.`)
    } else if (value === 'remote') {
      setLocation('Remote')
      setNotice('Saved. The next search will target remote roles.')
    }
  }

  async function researchGrowthOpportunities() {
    if (!single) return
    setGrowthResearchLoading(true)
    setCareerError('')
    try {
      const response = await fetch(`${API}/career/opportunities`, {
        credentials: 'include',
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: single.profile, location }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not search for development opportunities.')
      setGrowthResearch(data)
    } catch (err) {
      setCareerError(err instanceof Error ? err.message : 'Could not search for development opportunities.')
    } finally {
      setGrowthResearchLoading(false)
    }
  }

  async function loadCVReview(documentId: string, openWhenPending = true): Promise<CVInsightReview> {
    if (cvReview?.document_id === documentId && cvReview.language === locale) {
      if (openWhenPending && cvReview.review_status !== 'approved') setCvReviewOpen(true)
      return cvReview
    }
    setCvAnalyzing(true)
    setCvAnalysisError('')
    try {
      const response = await fetch(`${API}/documents/${documentId}/insights?locale=${locale}`, { credentials: 'include' })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || (locale === 'ar' ? 'تعذّر تحليل السيرة الذاتية.' : 'Could not review this CV.'))
      const review = data as CVInsightReview
      setCvReview(review)
      if (openWhenPending && review.review_status !== 'approved') setCvReviewOpen(true)
      return review
    } catch (err) {
      const message = err instanceof Error ? err.message : (locale === 'ar' ? 'تعذّر تحليل السيرة الذاتية.' : 'Could not review this CV.')
      setCvAnalysisError(message)
      throw err
    } finally {
      setCvAnalyzing(false)
    }
  }

  async function approveCVReview(): Promise<void> {
    if (!cvReview) return
    const response = await fetch(`${API}/documents/${cvReview.document_id}/insights/approve`, { method: 'POST', credentials: 'include' })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || (locale === 'ar' ? 'تعذّر اعتماد المراجعة.' : 'Could not approve the review.'))
    setCvReview(data)
    setCvReviewOpen(false)
    setNotice(locale === 'ar' ? 'تم اعتماد فهم السيرة. يمكنك بدء البحث الآن.' : 'CV understanding approved. You can start the search now.')
  }

  async function runSearch(forceBackground = false) {
    const selectedDocumentId = generatedCV?.documentId || savedCV?.documentId || ''
    if (!singleFile && selectedDocumentId) {
      try {
        const review = await loadCVReview(selectedDocumentId)
        if (review.review_status !== 'approved') return
      } catch { return }
    }
    setError(''); setCaptchaBlocked(false); setNotice(''); setLoading(true); setCareerPlan(null); setCareerError(''); setCareerCV(null); setGrowthResearch(null)
    setSearchProgress({
      id: 'starting', status: 'queued', stage: 'cv', progress: 4,
      headline: 'Preparing your search', detail: 'Connecting your CV to the live search workflow.',
      events: [{ id: 'starting', stage: 'cv', status: 'active', title: 'Preparing your search', detail: 'Securely loading your selected CV and search preferences.', meta: {} }],
    })
    try {
      const form = new FormData()
      form.append('location', location)
      form.append('limit', String(limit))
      form.append('live_browser', String(forceBackground ? false : liveBrowser))
      form.append('target_roles', targetRoles)
      form.append('excluded_title_terms', excludedTitleTerms)
      form.append('locale', locale)
      if (singleFile) form.append('cv', singleFile)
      else if (generatedCV) form.append('cv_document_id', generatedCV.documentId)
      else if (savedCV) form.append('cv_document_id', savedCV.documentId)
      else throw new Error('Upload a CV or create an ATS CV first.')
      const response = await fetch(`${API}/search-jobs`, { method: 'POST', body: form, credentials: 'include' })
      let progress: SearchProgressJob = await response.json()
      if (!response.ok) {
        const detail = (progress as unknown as { detail?: string | { message?: string } }).detail
        throw new Error(typeof detail === 'string' ? detail : detail?.message || 'Search failed')
      }
      setSearchProgress(progress)
      while (progress.status === 'queued' || progress.status === 'running') {
        await new Promise(resolve => window.setTimeout(resolve, 650))
        const statusResponse = await fetch(`${API}/search-jobs/${progress.id}`, { credentials: 'include' })
        const next: SearchProgressJob = await statusResponse.json()
        if (!statusResponse.ok) {
          const detail = (next as unknown as { detail?: string }).detail
          throw new Error(detail || 'Could not read search progress.')
        }
        progress = next
        setSearchProgress(progress)
      }
      if (progress.status === 'failed') throw new Error(progress.error || progress.detail || 'Search failed')
      if (!progress.result) throw new Error('Search completed without a result.')
      const data = progress.result
      const searchData: SearchData = {
        ...data,
        search_location: location.trim(),
        target_roles: targetRoles.trim(),
      }
      setSingle(searchData)
      setWorkspaceMode('opportunities')
      setResultFilter('all')
      setResultQuery('')
      setSelectedJobId(data.jobs?.[0]?.id ?? null)
      setBriefs({})
      setBriefErrors({})
      setSavedCV({
        documentId: data.document_id,
        sourceName: singleFile?.name || savedCV?.sourceName || 'Generated ATS CV',
      })
      if (data.jobs?.length) setSearchPanelOpen(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      setError(message)
      setCaptchaBlocked(message.toLowerCase().includes('verification') || message.toLowerCase().includes('captcha'))
    } finally {
      setLoading(false)
      setSearchProgress(null)
    }
  }

  async function prepareApplication(job: Job) {
    setError('')
    const response = await fetch(`${API}/application-draft`, {
      credentials: 'include',
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: job.title, company: job.company, keywords: job.keywords, profile: job.profile ?? {} }),
    })
    const data = await response.json()
    if (!response.ok) { setError(data.detail || 'Could not prepare application'); return }
    setDraft({ job, text: data.message })
  }

  async function startApplication(job: Job, autoSubmit: boolean) {
    setError(''); setNotice('')
    if (job.document_id) {
      try {
        const review = await loadCVReview(job.document_id)
        if (review.review_status !== 'approved') return
      } catch { return }
    }
    if (!job.direct_listing) { window.open(job.url, '_blank', 'noopener,noreferrer'); return }
    if (!job.document_id) { setError('This result does not have a reusable CV PDF. Run a single-CV search again.'); return }
    if (autoSubmit && !window.confirm('Wazzefni will prepare the form and submit only under this explicit approval. Continue?')) return
    const trackedResponse = await fetch(`${API}/applications`, {
      credentials: 'include',
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        opportunity_id: job.id, title: job.title, company: job.company, location: job.location,
        url: job.url, status: 'preparing', document_id: job.document_id, source: job.source,
        match_score: job.score, payload: { keywords: job.keywords },
      }),
    })
    const tracked = await trackedResponse.json()
    if (!trackedResponse.ok) { setError(tracked.detail || 'Could not create the application record'); return }
    let approvalId = ''
    if (autoSubmit) {
      const approvalResponse = await fetch(`${API}/agent/approvals`, {
        credentials: 'include',
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action_type: 'submit_application', summary: `Submit ${job.title} at ${job.company}`, target_type: 'application', target_id: tracked.id, payload: { title: job.title, company: job.company, url: job.url } }),
      })
      const approval = await approvalResponse.json()
      if (!approvalResponse.ok) { setError(approval.detail || 'Could not record submission approval'); return }
      const decisionResponse = await fetch(`${API}/agent/approvals/${approval.id}/decision`, {
        credentials: 'include',
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: 'approved', channel: 'app' }),
      })
      const decision = await decisionResponse.json()
      if (!decisionResponse.ok) { setError(decision.detail || 'Could not approve submission'); return }
      approvalId = decision.id
    }
    const response = await fetch(`${API}/application-sessions`, {
      credentials: 'include',
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: job.url,
        document_id: job.document_id,
        profile: { ...(job.profile ?? {}), application_answers: applicationAnswers },
        auto_submit: autoSubmit,
        application_id: tracked.id,
        opportunity_id: job.id,
        approval_id: approvalId,
        title: job.title,
        company: job.company,
        location: job.location,
        source: job.source,
        match_score: job.score,
      }),
    })
    const data = await response.json()
    if (!response.ok) { setError(data.detail || 'Could not start application automation'); return }
    setApplication(data)
    setApplicationJobId(job.id)
    setNotice('A visible application browser is running. Wazzefni will report exactly what it could fill.')
  }

  async function loadBrief(job: Job) {
    if (briefs[job.id] || briefLoading[job.id]) return
    setBriefLoading(current => ({ ...current, [job.id]: true }))
    setBriefErrors(current => ({ ...current, [job.id]: '' }))
    try {
      const response = await fetch(`${API}/job-brief`, {
        credentials: 'include',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: job.title,
          company: job.company,
          location: job.location,
          description: job.description,
          url: job.url,
          source: job.source,
          opportunity_type: job.opportunity_type,
        }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not build this job brief.')
      setBriefs(current => ({ ...current, [job.id]: data }))
    } catch (err) {
      setBriefErrors(current => ({
        ...current,
        [job.id]: err instanceof Error ? err.message : 'Could not build this job brief.',
      }))
    } finally {
      setBriefLoading(current => ({ ...current, [job.id]: false }))
    }
  }

  function toggleSaved(jobId: string) {
    setSavedJobIds(current => {
      const next = current.includes(jobId) ? current.filter(id => id !== jobId) : [...current, jobId]
      localStorage.setItem('wazzefni-saved-jobs', JSON.stringify(next))
      void fetch(`${API}/opportunities/${jobId}/status`, {
        credentials: 'include',
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: next.includes(jobId) ? 'saved' : 'discovered' }),
      }).catch(() => { /* Keep the optimistic local state while offline. */ })
      return next
    })
  }

  function selectJob(jobId: string) {
    setSelectedJobId(jobId)
    if (window.matchMedia('(max-width: 780px)').matches) {
      window.setTimeout(() => document.getElementById('job-brief')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 40)
    }
  }

  async function fileChosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.currentTarget.value = ''
    if (!file) return
    setCvAnalyzing(true)
    setCvAnalysisError('')
    setError('')
    try {
      const body = new FormData()
      body.append('cv', file)
      body.append('locale', locale)
      const response = await fetch(`${API}/documents`, { method: 'POST', credentials: 'include', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || (locale === 'ar' ? 'تعذّر تحليل السيرة الذاتية.' : 'Could not analyze this CV.'))
      const review = { document_id: data.document.id, ...data.insights } as CVInsightReview
      setSingleFile(null)
      setGeneratedCV(null)
      setSavedCV({ documentId: data.document.id, sourceName: data.document.source_name })
      setCvReview(review)
      setCvReviewOpen(true)
    } catch (err) {
      const message = err instanceof Error ? err.message : (locale === 'ar' ? 'تعذّر تحليل السيرة الذاتية.' : 'Could not analyze this CV.')
      setCvAnalysisError(message)
      setError(message)
    } finally {
      setCvAnalyzing(false)
    }
  }

  const authMode = browserLocation.pathname === '/signup' ? 'signup' : browserLocation.pathname === '/forgot-password' ? 'forgot-password' : browserLocation.pathname === '/reset-password' ? 'reset-password' : browserLocation.pathname === '/login' ? 'login' : null
  if (authMode) return <AuthPage mode={authMode} knownName={identity.name} onComplete={next => { if (next.locale) setLocale(next.locale); setIdentity(next); setAuthState('authenticated') }}/>
  if (authState === 'checking') return <main className="session-loading"><BrandLogo/><span>Opening your workspace…</span></main>
  if (authState === 'anonymous') return <Navigate to="/login" replace/>

  const runtimeOffline = modelLabel === 'Backend offline'
  const [runtimeModel, runtimeLocation] = modelLabel.split(' · ')

  const workspaceMeta = {
    today: ['TODAY', 'Your step today', 'One qualification or application action, chosen from your real evidence.'],
    career: ['DEVELOPMENT', 'Build your path to the role', 'Readiness, qualification, skill proof, and interview practice in one connected workspace.'],
    readiness: ['READINESS', 'Your readiness', 'See what is proved, what is missing, and which path is realistic now.'],
    development: ['QUALIFICATION PLAN', 'Your qualification plan', 'Build the evidence that unlocks stronger training and job opportunities.'],
    proof: ['SKILL PROOF', 'Prove what you can do', 'Assessment based on your explanation, reasoning, and inspectable work.'],
    opportunities: resultFilter === 'saved'
      ? ['', 'Your saved roles', 'Keep your favorite opportunities in one place.']
      : ['', 'Opportunity workspace', 'Search, compare, and act on roles matched to your actual profile.'],
    growth: ['MARKET RESEARCH', 'Find useful growth opportunities.', 'Research is supporting evidence for your qualification plan.'],
    applications: ['APPLICATIONS', 'Every application, one history', 'Track the evidence, conversations, next action, and outcome.'],
    interviews: ['DEVELOPMENT · PRACTICE', 'Practice against the actual role', 'Text and voice coaching grounded in your confirmed experience.'],
    offers: ['OFFERS', 'Decide with the full picture', 'Compare stated terms and prepare a response without invented leverage.'],
    profile: locale === 'ar' ? ['بياناتي', 'بياناتك وسيرتك الذاتية', 'عدّل معلوماتك وغيّر السيرة المستخدمة وراجع أي استنتاج قبل حفظه.'] : ['MY PROFILE', 'Your data and CV', 'Edit your information, change the active CV, and review every inference before it is saved.'],
    settings: ['SETTINGS', 'Settings', 'Manage your account, preferences, notifications, and AI runtime.'],
  }[workspaceMode]
  const developmentSectionActive = ['career', 'readiness', 'development', 'proof', 'interviews', 'growth'].includes(workspaceMode)

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand"><BrandLogo/></div>
      <p className="nav-title">Workspace</p>
      <button title="Your step today" aria-label="Your step today" className={workspaceMode === 'today' ? 'nav-active' : 'nav'} onClick={() => setWorkspaceMode('today')}><Home size={17}/><span className="nav-label">Your step today</span></button>
      <p className="nav-title nav-title-secondary">Develop</p>
      <button title="Career development" aria-label="Career development" className={developmentSectionActive ? 'nav-active' : 'nav'} onClick={() => setWorkspaceMode('career')}><GraduationCap size={17}/><span className="nav-label">Career development</span></button>
      <p className="nav-title nav-title-secondary">Find work</p>
      <button title="Opportunities" aria-label="Opportunities" className={workspaceMode === 'opportunities' && resultFilter !== 'saved' ? 'nav-active' : 'nav'} onClick={() => { setWorkspaceMode('opportunities'); setResultFilter('all') }}><BriefcaseBusiness size={17}/><span className="nav-label">Opportunities</span>{jobs.length > 0 && <span className="nav-count">{jobs.length}</span>}</button>
      <button title="Applications" aria-label="Applications" className={workspaceMode === 'applications' ? 'nav-active' : 'nav'} onClick={() => setWorkspaceMode('applications')}><LayoutList size={17}/><span className="nav-label">Applications</span></button>
      <button title="Saved roles" aria-label="Saved roles" className={workspaceMode === 'opportunities' && resultFilter === 'saved' ? 'nav-active' : 'nav'} onClick={() => { setWorkspaceMode('opportunities'); setResultFilter('saved'); setSearchPanelOpen(false) }}><Bookmark size={17}/><span className="nav-label">Saved</span>{savedCount > 0 && <span className="nav-count">{savedCount}</span>}</button>
      <button title="Offers" aria-label="Offers" className={workspaceMode === 'offers' ? 'nav-active' : 'nav'} onClick={() => setWorkspaceMode('offers')}><CircleDollarSign size={17}/><span className="nav-label">Offers</span></button>
      <button title={locale === 'ar' ? 'بياناتي والسيرة الذاتية' : 'My data & CV'} aria-label={locale === 'ar' ? 'بياناتي والسيرة الذاتية' : 'My data and CV'} className={workspaceMode === 'profile' ? 'nav-active' : 'nav'} onClick={() => setWorkspaceMode('profile')}><UserRound size={17}/><span className="nav-label">{locale === 'ar' ? 'بياناتي والسيرة الذاتية' : 'My data & CV'}</span></button>
      <button title="Settings" aria-label="Settings" className={workspaceMode === 'settings' ? 'nav-active settings-nav' : 'nav settings-nav'} onClick={() => setWorkspaceMode('settings')}><Settings size={17}/><span className="nav-label">Settings</span></button>
      <button className="side-bottom" type="button" onClick={() => setSettingsOpen(true)} aria-label={locale === 'ar' ? `محرك الذكاء الاصطناعي: ${modelLabel}. فتح إعدادات المحرك` : `AI runtime: ${modelLabel}. Open model settings`}>
        <span className="side-runtime-icon"><Bot size={18}/></span>
        <span className="side-runtime-copy">
          <small>AI runtime</small>
          <b><span className={`model-dot ${runtimeOffline ? 'offline' : ''}`}/>{runtimeOffline ? 'Offline' : runtimeLocation === 'local' ? 'Local and ready' : 'Cloud ready'}</b>
          <em title={modelLabel}>{runtimeModel}</em>
        </span>
        <ChevronRight className="side-runtime-arrow" size={16}/>
      </button>
    </aside>

    <nav className="mobile-nav" aria-label={t('Primary navigation')}>
      <button aria-label="Today" className={workspaceMode === 'today' ? 'active' : ''} onClick={() => { setWorkspaceMode('today'); setMobileMenuOpen(false) }}><Home size={18}/><span>Today</span></button>
      <button aria-label="Career development" className={developmentSectionActive ? 'active' : ''} onClick={() => { setWorkspaceMode('career'); setMobileMenuOpen(false) }}><GraduationCap size={18}/><span>Develop</span></button>
      <button aria-label="Jobs" className={workspaceMode === 'opportunities' ? 'active' : ''} onClick={() => { setWorkspaceMode('opportunities'); setResultFilter('all'); setMobileMenuOpen(false) }}><BriefcaseBusiness size={18}/><span>Jobs</span></button>
      <button aria-label={t('Application pipeline')} className={workspaceMode === 'applications' ? 'active' : ''} onClick={() => { setWorkspaceMode('applications'); setMobileMenuOpen(false) }}><LayoutList size={18}/><span>Pipeline</span></button>
      <button aria-label="More" className={mobileMenuOpen || ['offers', 'growth', 'profile', 'settings'].includes(workspaceMode) ? 'active' : ''} aria-expanded={mobileMenuOpen} aria-controls="mobile-more-menu" onClick={() => setMobileMenuOpen(value => !value)}><Menu size={18}/><span>More</span></button>
    </nav>
    {mobileMenuOpen && <div className="mobile-more-menu" id="mobile-more-menu">
      <button onClick={() => { setWorkspaceMode('offers'); setMobileMenuOpen(false) }}><CircleDollarSign size={17}/> Offers</button>
      <button onClick={() => { setWorkspaceMode('opportunities'); setResultFilter('saved'); setMobileMenuOpen(false) }}><Bookmark size={17}/> Saved roles</button>
      <button onClick={() => { setWorkspaceMode('profile'); setMobileMenuOpen(false) }}><UserRound size={17}/> Profile & integrations</button>
      <button onClick={() => { setWorkspaceMode('settings'); setMobileMenuOpen(false) }}><Settings size={17}/> Settings</button>
      {installPrompt && <button onClick={() => { void installApp(); setMobileMenuOpen(false) }}><Download size={17}/> Install Wazzefni</button>}
    </div>}

    <section className="content">
      <header className="workspace-header">
        <div>
          {workspaceMeta[0] && <p className="eyebrow">{workspaceMeta[0]}</p>}
          <h1>{workspaceMeta[1]}</h1>
          <p className="header-copy">{workspaceMeta[2]}</p>
        </div>
        <div className="header-utilities">
          <label className="global-search"><Search size={17}/><input aria-label="Search Wazzefni" placeholder="Search jobs, companies, or skills..."/></label>
          <div className="notifications-control" ref={notificationsRef}>
            <button
              className="notification-button"
              aria-label={unreadNotificationCount ? `Notifications, ${unreadNotificationCount} unread` : 'Notifications'}
              aria-expanded={notificationsOpen}
              aria-controls="notifications-popover"
              aria-haspopup="true"
              onClick={() => {
                const nextOpen = !notificationsOpen
                setNotificationsOpen(nextOpen)
                if (nextOpen && notifications.length) {
                  setReadNotificationIds(current => Array.from(new Set([...current, ...notifications.map(item => item.id)])))
                }
              }}
            >
              <Bell size={18}/>
              {unreadNotificationCount > 0 && <span className="notification-indicator"/>}
            </button>
            {notificationsOpen && <section className="notifications-popover" id="notifications-popover" aria-label="Notifications">
              <div className="notifications-heading"><div><small>UPDATES</small><h2>Notifications</h2></div><span>{notifications.length}</span></div>
              {notifications.length > 0
                ? <div className="notification-list">{notifications.map(item => <button key={item.id} type="button" onClick={() => { setWorkspaceMode(item.target); setNotificationsOpen(false) }}><span><Bell size={15}/></span><div><b>{item.title}</b><p>{item.detail}</p></div><ChevronRight size={16}/></button>)}</div>
                : <div className="notifications-empty"><span><Bell size={20}/></span><b>You’re all caught up</b><p>New application and interview updates will appear here.</p></div>}
            </section>}
          </div>
          <button className="avatar-button" aria-label={locale === 'ar' ? `فتح الملف الشخصي لـ ${identity.name || 'المستخدم'}` : identity.name ? `Open ${identity.name}'s profile` : 'Open profile'} onClick={() => setWorkspaceMode('profile')}><UserAvatar name={identity.name} src={identity.avatarUrl}/></button>
          <button className="mobile-settings" aria-label="Open settings" onClick={() => setWorkspaceMode('settings')}><Settings size={18}/></button>
        </div>
      </header>
      {workspaceMode === 'growth' && <img className="growth-header-illustration" src="/jobflow-assistant.svg" alt=""/>}

      {workspaceMode === 'today' ? <TodayPage onNavigate={page => setWorkspaceMode(page as WorkspaceMode)}/> : workspaceMode === 'career' ? <CareerDevelopmentHub onNavigate={page => setWorkspaceMode(page as WorkspaceMode)}/> : workspaceMode === 'readiness' ? <ReadinessPage onNavigate={page => setWorkspaceMode(page as WorkspaceMode)}/> : workspaceMode === 'development' ? <QualificationPlanPage onNavigate={page => setWorkspaceMode(page as WorkspaceMode)}/> : workspaceMode === 'proof' ? <SkillProofPage onNavigate={page => setWorkspaceMode(page as WorkspaceMode)}/> : workspaceMode === 'applications' ? <ApplicationsPage/> : workspaceMode === 'interviews' ? <InterviewsPage/> : workspaceMode === 'offers' ? <OffersPage/> : workspaceMode === 'profile' ? <ProfilePage/> : workspaceMode === 'settings' ? <SettingsPage modelLabel={modelLabel} onOpenModel={() => setSettingsOpen(true)} onIdentityChange={setIdentity} onSignOut={async () => { await fetch(`${API}/auth/logout`, { method: 'POST', credentials: 'include' }); setAuthState('anonymous'); setIdentity({ name: '', email: '' }); navigate('/login') }}/> : workspaceMode === 'growth' ? <GrowthWorkspace
        hasSearch={Boolean(single?.jobs.length)}
        plan={careerPlan}
        loading={careerLoading}
        error={careerError}
        answerBusy={careerAnswerBusy}
        cvUpdate={careerCV}
        research={growthResearch}
        researchLoading={growthResearchLoading}
        onAnswer={saveCareerAnswer}
        onDecision={saveCareerDecision}
        onResearch={researchGrowthOpportunities}
        onSearch={() => { setWorkspaceMode('opportunities'); setSearchPanelOpen(true) }}
      /> : <>
      {searchPanelOpen && resultFilter !== 'saved' ? (loading && searchProgress ? <SearchActivity progress={searchProgress}/> : <>
        <div className="reference-search-layout">
          <section className="search-panel" aria-busy={loading}>
            <div className="panel-heading">
              <div><h2>Find your next opportunity</h2><p>Upload your CV and tell us what you're looking for. We'll find and match the best opportunities for you.</p></div>
              {jobs.length > 0 && <button className="panel-collapse" onClick={() => setSearchPanelOpen(false)}><ChevronUp size={15}/> Close</button>}
            </div>
            {generatedCV && <p className="generated-ready"><CheckCircle2 size={14}/> ATS PDF generated and selected. <a href={`${API_ORIGIN}${generatedCV.pdfUrl}`} target="_blank" rel="noreferrer">Open PDF</a></p>}
            <label className="upload-zone">
              <input type="file" accept=".pdf,.txt" disabled={loading || cvAnalyzing} onChange={fileChosen}/>
              <span className="upload-icon">{cvAnalyzing ? <RefreshCw className="spin" size={27}/> : <UploadCloud size={27}/>}</span>
              <span className="upload-copy"><b>{cvAnalyzing ? (locale === 'ar' ? 'بنحلل سيرتك دلوقتي…' : 'Reviewing your CV…') : singleFile?.name ?? (generatedCV ? 'Generated CV selected' : savedCV ? savedCV.sourceName : 'Choose your CV')}</b><small>{cvAnalyzing ? (locale === 'ar' ? 'بنستخرج المعلومات المكتوبة ونفصلها عن الاستنتاجات.' : 'Separating written facts from AI-derived conclusions.') : savedCV && !singleFile && !generatedCV ? 'Saved and ready to reuse' : 'Upload a PDF or TXT file (max 5 MB)'}</small><em>Or <button type="button" disabled={loading || cvAnalyzing} onClick={event => { event.preventDefault(); setCvBuilderOpen(true) }}>Build a CV instead <ArrowUpRight size={13}/></button></em></span>
              <span className="upload-cta">{cvAnalyzing ? (locale === 'ar' ? 'جارٍ التحليل' : 'Analyzing') : 'Upload CV'}</span>
            </label>
            {cvAnalysisError && <p className="cv-card-error">{cvAnalysisError}</p>}
            <div className="search-core">
              <label className="field"><span>Location</span><div><MapPin size={17}/><input disabled={loading} value={location} onChange={event => setLocation(event.target.value)} placeholder="Cairo or Remote"/></div></label>
              <label className="field result-count"><span>Results per page</span><div><LayoutList size={17}/><select disabled={loading} value={limit} onChange={event => setLimit(Number(event.target.value))}>{[3, 5, 10].map(value => <option value={value} key={value}>{t(`${value} roles`)}</option>)}</select></div></label>
            </div>
            <button className="preferences-toggle" aria-expanded={preferencesOpen} onClick={() => setPreferencesOpen(value => !value)}>Search preferences <span>(optional)</span>{preferencesOpen ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}</button>
            {preferencesOpen && <div className="preference-grid">
              <label className="field"><span>Specific roles</span><div><Search size={15}/><input disabled={loading} value={targetRoles} onChange={event => setTargetRoles(event.target.value)} placeholder="e.g. Product Designer, Data Analyst"/></div></label>
              <label className="field"><span>Exclude titles</span><div><X size={15}/><input disabled={loading} value={excludedTitleTerms} onChange={event => setExcludedTitleTerms(event.target.value)} placeholder="e.g. Intern, Volunteer"/></div></label>
              <label className="watch-toggle"><span>Show search browser</span><span className="toggle-line"><input type="checkbox" disabled={loading} checked={liveBrowser} onChange={event => setLiveBrowser(event.target.checked)}/><small>Show live search results in a new tab</small></span></label>
            </div>}
            <button className="search-button" onClick={() => runSearch()} disabled={loading}><Search size={20}/>{loading ? 'Searching...' : 'Find roles'}<ArrowUpRight size={17}/></button>
          </section>
          <aside className="search-side" aria-label={t('How Wazzefni helps')}>
            <section className="search-companion">
              <div className="companion-copy"><h3>{locale === 'ar' ? <>تأهّل أولًا،<br/>ثم احصل على الوظيفة.</> : <>Get ready,<br/>then get hired.</>}</h3><p>Wazzefni finds the gaps, helps you prove the missing skills, then brings the right opportunities into reach.</p><button onClick={() => setWorkspaceMode('readiness')}>Check readiness <ArrowUpRight size={14}/></button></div>
              <img src="/jobflow-assistant.svg" alt={t('Wazzefni helping someone build job readiness')}/>
            </section>
            <section className="search-benefits">
              <div><span><Target size={20}/></span><p><b>Personalized matches</b><small>Opportunities that fit your skills</small></p></div>
              <div><span><Sparkles size={20}/></span><p><b>Save time</b><small>We do the searching for you</small></p></div>
              <div><span><BarChart3 size={20}/></span><p><b>More relevant results</b><small>From top companies, worldwide</small></p></div>
            </section>
          </aside>
        </div>
      </>) : <>
        <section className={`reference-overview ${resultFilter === 'saved' ? 'saved-overview' : ''}`}>
          {resultFilter === 'saved' ? <div className="saved-summary-card"><span><Bookmark size={30}/></span><div><b>{savedCount} saved role{savedCount === 1 ? '' : 's'}</b><p>Great choices! You can compare, prepare and apply when you're ready.</p></div></div> : <div className="reference-stats">
            <article><span><FileText size={23}/></span><div><b>Active CV</b><strong>{savedCV?.sourceName || singleFile?.name || 'Your CV'}</strong><small>Ready for applications</small></div></article>
            <article><span><MapPin size={23}/></span><div><b>Location</b><strong>{single?.search_location || location}</strong><small>Open to current search</small></div></article>
            <article><span><BarChart3 size={23}/></span><div><b>{single ? single.qualified + single.review : jobs.length}</b><strong>CV-matched roles</strong><small>{single?.discovered || jobs.length} current listings checked</small></div></article>
          </div>}
          <aside className="reference-promo"><div><b>{resultFilter === 'saved' ? 'Good opportunities lead to great things' : 'Build proof before you apply'}</b><p>{resultFilter === 'saved' ? "Keep exploring and make your next move. You've got this!" : 'Our AI separates what you can apply for now from what you can unlock next.'}</p>{resultFilter !== 'saved' && <button onClick={() => setWorkspaceMode('readiness')}>Check readiness <ArrowUpRight size={13}/></button>}</div><img src="/jobflow-assistant.svg" alt=""/></aside>
        </section>

        <section className={`jobs-workbench ${resultFilter === 'saved' ? 'saved-workbench' : ''}`}>
          <div className="job-list" aria-label="Matching opportunities">
            <div className="job-list-heading"><div><h2>{resultFilter === 'saved' ? 'Saved roles' : 'Opportunities for You'}</h2>{resultFilter !== 'saved' && <p>Ranked by readiness and verified evidence—not acceptance probability</p>}</div><button>{resultFilter === 'saved' ? 'Recently saved' : 'Best readiness'}<ChevronDown size={15}/></button></div>
            {resultFilter !== 'saved' && <div className="opportunity-tracks" aria-label="Opportunity readiness tracks">
              <button className={resultFilter === 'all' ? 'active' : ''} onClick={() => setResultFilter('all')}>All <span>{jobs.length}</span></button>
              <button className={resultFilter === 'ready' ? 'active' : ''} onClick={() => setResultFilter('ready')}>Apply now <span>{jobs.filter(job => job.status === 'ready' && job.score >= .8).length}</span></button>
              <button className={resultFilter === 'improve' ? 'active' : ''} onClick={() => setResultFilter('improve')}>Apply while improving <span>{jobs.filter(job => job.status === 'ready' && job.score >= .65 && job.score < .8).length}</span></button>
              <button className={resultFilter === 'unlock' ? 'active' : ''} onClick={() => setResultFilter('unlock')}>Unlock later <span>{jobs.filter(job => job.status !== 'ready' || job.score < .65).length}</span></button>
              <button className={resultFilter === 'training' ? 'active' : ''} onClick={() => setResultFilter('training')}>Training</button>
            </div>}
            {visibleJobs.length ? visibleJobs.map(job => <JobRow job={job} key={job.id} selected={selectedJob?.id === job.id} saved={savedJobIds.includes(job.id)} onSelect={() => selectJob(job.id)} onToggleSaved={() => toggleSaved(job.id)}/>) : <section className="filtered-empty"><Bookmark size={24}/><h3>No saved roles yet.</h3><p>Save an opportunity and it will appear here.</p><button onClick={() => { setResultFilter('all'); setSearchPanelOpen(Boolean(!jobs.length)) }}>Browse opportunities</button></section>}
            {visibleJobs.length > 0 && <footer className="job-list-footer"><span>Showing {visibleJobs.length} of {single ? single.qualified + single.review : jobs.length} matched roles · {single?.discovered || jobs.length} listings checked</span><button onClick={() => setLimit(current => Math.min(10, current + 5))}>Load more jobs <ChevronDown size={14}/></button></footer>}
          </div>
          <JobInspector
            key={selectedJob?.id || 'empty'}
            job={selectedJob}
            brief={selectedJob ? briefs[selectedJob.id] : undefined}
            loading={selectedJob ? Boolean(briefLoading[selectedJob.id]) : false}
            error={selectedJob ? briefErrors[selectedJob.id] : ''}
            saved={selectedJob ? savedJobIds.includes(selectedJob.id) : false}
            onRetry={() => selectedJob && loadBrief(selectedJob)}
            onToggleSaved={() => selectedJob && toggleSaved(selectedJob.id)}
            onPrepare={prepareApplication}
            onApply={startApplication}
            onOutreach={(job, companyUrl) => setOutreachContext({ job, companyUrl })}
          />
        </section>
      </>}

      {(error || notice) && <div className="feedback-stack" aria-live="polite">
        {error && <div className="feedback error-feedback"><span>{error}</span><button aria-label="Dismiss error" onClick={() => { setError(''); setCaptchaBlocked(false) }}><X size={15}/></button></div>}
        {captchaBlocked && <button className="captcha-retry" onClick={() => runSearch(true)} disabled={loading}>Retry with the browser hidden</button>}
        {notice && <div className="feedback notice-feedback"><span>{notice}</span><button aria-label="Dismiss notice" onClick={() => setNotice('')}><X size={15}/></button></div>}
      </div>}

      {searchPanelOpen && resultFilter !== 'saved' && !jobs.length && !loading && <section className="empty reference-start"><div className="empty-illustration"><FileText size={48}/><Sparkles size={22}/></div><h2>Start with your CV.</h2><p>Upload your CV and we'll match opportunities to your skills and goals.</p></section>}
      </>}
    </section>
    {draft && <DraftModal draft={draft} onClose={() => setDraft(null)}/>}
    {cvBuilderOpen && <CVBuilder onClose={() => setCvBuilderOpen(false)} onUse={cv => { setGeneratedCV(cv); setSavedCV({ documentId: cv.documentId, sourceName: 'Generated ATS CV' }); setSingleFile(null); setCvBuilderOpen(false); void loadCVReview(cv.documentId) }}/>}
    {cvReviewOpen && cvReview && <CVInsightsReview
      review={cvReview}
      locale={locale}
      onClose={() => setCvReviewOpen(false)}
      onReviewChange={setCvReview}
      onApprove={approveCVReview}
    />}
    {settingsOpen && <SettingsModal
      onClose={() => setSettingsOpen(false)}
      onSaved={settings => {
        setModelLabel(`${settings.model} · ${settings.provider === 'ollama_local' ? 'local' : 'cloud'}`)
        setSettingsOpen(false)
      }}
    />}
    {outreachContext && <OutreachModal
      context={outreachContext}
      profile={outreachContext.job.profile ?? {}}
      onClose={() => setOutreachContext(null)}
    />}
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
      localStorage.setItem('wazzefni-application-answers', JSON.stringify(updated))
    }}/>}<ProfileDataPrompt/>
  </main>
}

function CVInsightsReview({ review, locale, onClose, onReviewChange, onApprove }: {
  review: CVInsightReview; locale: 'en' | 'ar'; onClose: () => void
  onReviewChange: (review: CVInsightReview) => void; onApprove: () => Promise<void>
}) {
  const [selectedId, setSelectedId] = useState('')
  const [requestedValue, setRequestedValue] = useState('')
  const [detail, setDetail] = useState('')
  const [history, setHistory] = useState<{ role: 'user' | 'assistant'; content: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [approving, setApproving] = useState(false)
  const [discussionPending, setDiscussionPending] = useState(false)
  const [error, setError] = useState('')
  const arabic = locale === 'ar'
  const selected = review.insights.find(item => item.id === selectedId)
  const valueText = (value: string | string[]) => Array.isArray(value) ? value.join('، ') : String(value)
  const pathLabel = review.recommendation.path === 'internship'
    ? (arabic ? 'تدريب' : 'Internship')
    : review.recommendation.path === 'job' ? (arabic ? 'وظيفة' : 'Job') : (arabic ? 'وظيفة أو تدريب' : 'Job or internship')

  function openDiscussion(insight: CVInsight) {
    setSelectedId(insight.id)
    setRequestedValue(valueText(insight.value))
    setDetail('')
    setHistory([])
    setDiscussionPending(false)
    setError('')
  }

  async function sendDiscussion() {
    if (!selected || !requestedValue.trim()) return
    setBusy(true)
    setError('')
    const userMessage = detail.trim() || (arabic ? `عايز أغيّر القيمة إلى: ${requestedValue}` : `I want to change the value to: ${requestedValue}`)
    const nextHistory = [...history, { role: 'user' as const, content: userMessage }]
    try {
      const response = await fetch(`${API}/documents/${review.document_id}/insights/challenge`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ insight_id: selected.id, requested_value: requestedValue, message: userMessage, history: nextHistory, locale }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || (arabic ? 'تعذّر إكمال النقاش.' : 'Could not continue the discussion.'))
      const assistantMessage = data.discussion.follow_up_question || data.discussion.message
      setHistory([...nextHistory, { role: 'assistant', content: assistantMessage }])
      setDiscussionPending(data.discussion.status === 'needs_evidence')
      setDetail('')
      onReviewChange(data.review)
    } catch (err) {
      setError(err instanceof Error ? err.message : (arabic ? 'تعذّر إكمال النقاش.' : 'Could not continue the discussion.'))
    } finally {
      setBusy(false)
    }
  }

  async function approve() {
    setApproving(true)
    setError('')
    try { await onApprove() }
    catch (err) { setError(err instanceof Error ? err.message : (arabic ? 'تعذّر اعتماد المراجعة.' : 'Could not approve this review.')) }
    finally { setApproving(false) }
  }

  return <div className="modal-backdrop cv-insights-backdrop"><section className="cv-insights-review" role="dialog" aria-modal="true" aria-label={arabic ? 'مراجعة فهم السيرة الذاتية' : 'Review CV understanding'}>
    <button className="cv-insights-close" onClick={onClose} aria-label={arabic ? 'إغلاق' : 'Close'}><X size={19}/></button>
    <header className="cv-insights-head"><span><Sparkles size={20}/></span><p>{arabic ? 'تحليل السيرة اكتمل' : 'CV REVIEW COMPLETE'}</p><h2>{arabic ? 'ده فهمنا لسيرتك قبل ما نبحث.' : 'Here’s what we understood before searching.'}</h2><small>{review.summary}</small></header>
    <section className="cv-recommendation"><div><p>{arabic ? 'المسار الأنسب حاليًا' : 'BEST-FIT PATH'}</p><h3>{pathLabel} · {review.recommendation.level}</h3><div>{review.recommendation.role_titles.map(role => <span key={role}>{role}</span>)}</div></div><aside><b>{Math.round(review.recommendation.confidence * 100)}%</b><span>{arabic ? 'ثقة في التقييم' : 'assessment confidence'}</span></aside><p>{review.recommendation.reason}</p></section>
    <div className="cv-insight-legend"><span className="explicit">{arabic ? 'مكتوب في السيرة' : 'Written in CV'}</span><span className="derived">{arabic ? 'استنتاج من التحليل' : 'AI-derived'}</span><span className="user_claim">{arabic ? 'تعديل منك غير موثّق' : 'Unverified user change'}</span></div>
    <div className="cv-insight-list">{review.insights.map(insight => <article key={insight.id} className={selectedId === insight.id ? 'selected' : ''}><div className="cv-insight-title"><span className={insight.basis}>{insight.basis === 'explicit' ? (arabic ? 'مكتوب' : 'CV fact') : insight.basis === 'user_claim' ? (arabic ? 'منك' : 'Your claim') : (arabic ? 'استنتاج' : 'Derived')}</span><b>{insight.label}</b></div><strong>{valueText(insight.value)}</strong><p>{insight.explanation}</p>{insight.evidence_quotes.length > 0 && <blockquote>“{insight.evidence_quotes[0]}”</blockquote>}{insight.user_evidence?.length ? <small>{arabic ? 'الدليل الذي ذكرته: ' : 'Evidence you provided: '}{insight.user_evidence.join(' · ')}</small> : null}<button onClick={() => openDiscussion(insight)}>{arabic ? 'أناقش أو أغيّر' : 'Discuss or change'}</button></article>)}</div>
    {selected && <section className="cv-insight-discussion"><div className="discussion-heading"><div><p>{arabic ? 'مراجعة دقيقة' : 'EVIDENCE REVIEW'}</p><h3>{selected.label}</h3></div><button onClick={() => { setSelectedId(''); setHistory([]); setDiscussionPending(false) }}><X size={15}/>{arabic ? 'إلغاء التعديل' : 'Cancel change'}</button></div><label><span>{arabic ? 'القيمة التي تقترحها' : 'Your proposed value'}</span><input value={requestedValue} onChange={event => setRequestedValue(event.target.value)}/></label>{history.length > 0 && <div className="discussion-thread">{history.map((message, index) => <p className={message.role} key={`${message.role}-${index}`}>{message.content}</p>)}</div>}<label><span>{history.length ? (arabic ? 'ردّك والدليل المتاح' : 'Your reply and available evidence') : (arabic ? 'اشرح ليه القيمة الحالية مش صحيحة' : 'Explain why the current value is wrong')}</span><textarea rows={3} value={detail} onChange={event => setDetail(event.target.value)} placeholder={arabic ? 'مثال: اشتغلت في شركة كذا من شهر كذا لسنة كذا…' : 'Example: I worked at Company X from month/year to month/year…'}/></label><button className="os-primary" disabled={busy || !requestedValue.trim()} onClick={sendDiscussion}>{busy ? (arabic ? 'بنراجع الدليل…' : 'Reviewing evidence…') : history.length ? (arabic ? 'إرسال الرد' : 'Send reply') : (arabic ? 'ابدأ النقاش' : 'Start discussion')}<ArrowUpRight size={15}/></button></section>}
    {error && <p className="cv-insights-error">{error}</p>}
    <footer><div><ShieldCheck size={17}/><p><b>{arabic ? 'الشركة تشوف معلومات قابلة للدفاع عنها فقط.' : 'Employers only see defensible information.'}</b><span>{review.source_note}</span></p></div><button className="os-primary" disabled={approving || discussionPending} onClick={approve}>{approving ? (arabic ? 'جارٍ الاعتماد…' : 'Approving…') : (arabic ? 'المعلومات صحيحة — كمل' : 'Everything looks right — continue')}<ArrowUpRight size={16}/></button></footer>
  </section></div>
}

function CoachStrip({ plan, loading, error, onOpen }: { plan: AcceptancePlan | null; loading: boolean; error: string; onOpen: () => void }) {
  if (loading) return <section className="coach-strip loading" aria-live="polite"><span className="coach-orbit"><RefreshCw className="spin" size={15}/></span><div><b>Found the jobs. Now checking what would improve your odds.</b><small>Comparing the current listings with evidence already in your CV.</small></div></section>
  if (error) return <section className="coach-strip"><span className="coach-orbit muted"><Target size={15}/></span><div><b>The jobs are ready; the acceptance plan needs another try.</b><small>{error}</small></div><button onClick={onOpen}>Open plan</button></section>
  if (!plan) return null
  return <section className="coach-strip" aria-label="Acceptance agent update">
    <span className="coach-orbit"><Target size={15}/></span>
    <div><b>{plan.message}</b><small>{plan.question ? `Next question · ${plan.question.question}` : plan.source_note}</small></div>
    <button onClick={onOpen}>{plan.question ? 'Answer once' : 'View plan'}<ArrowUpRight size={14}/></button>
  </section>
}

function GrowthWorkspace({ hasSearch, plan, loading, error, answerBusy, cvUpdate, research, researchLoading, onAnswer, onDecision, onResearch, onSearch }: {
  hasSearch: boolean; plan: AcceptancePlan | null; loading: boolean; error: string; answerBusy: boolean
  cvUpdate: CareerCVUpdate | null; research: GrowthResearch | null; researchLoading: boolean
  onAnswer: (question: CareerQuestion, value: string) => Promise<boolean>
  onDecision: (decision: CareerDecision, value: string) => Promise<void>
  onResearch: () => Promise<void>; onSearch: () => void
}) {
  const [typedAnswer, setTypedAnswer] = useState('')
  const [selectedAnswer, setSelectedAnswer] = useState('')
  useEffect(() => { setTypedAnswer(''); setSelectedAnswer('') }, [plan?.question?.memory_key])

  if (!hasSearch) return <section className="growth-empty"><div><Target size={25}/></div><p className="eyebrow">NEEDS A MARKET SAMPLE</p><h2>Search once, then I can choose the right next move.</h2><p>The plan compares your actual CV with actual listings. It will not give you a generic skills checklist.</p><button onClick={onSearch}><Search size={15}/> Find roles first</button></section>
  if (loading && !plan) return <section className="growth-loading"><div className="agent-pulse"><Target size={19}/></div><p className="eyebrow">BUILDING YOUR PLAN</p><h2>Reading the current market evidence…</h2><div className="growth-skeleton"><i/><i/><i/></div></section>
  if (!plan) return <section className="growth-empty"><div><Target size={25}/></div><h2>Could not build the plan yet.</h2><p>{error || 'Run a fresh search and try again.'}</p><button onClick={onSearch}>Back to search</button></section>

  const rememberedCount = Object.keys(plan.remembered || {}).length
  return <section className="growth-workspace">
    <div className="agent-summary">
      <div className="agent-bot"><Bot size={45}/></div>
      <div className="agent-identity"><div><b>Your Acceptance Agent</b><small>I'm analyzing your profile and the market to help you improve your chances. Let's take the next step together.</small><i><span/>Analyzing your preferences...</i></div></div>
      <ol className="agent-activity">{plan.activities.slice(0, 4).map((activity, index) => <li className={activity.state} key={`${activity.label}-${index}`}><span>{activity.state === 'done' ? <Check size={13}/> : index + 1}</span><b>{activity.label}</b><small>{activity.state === 'done' ? 'Completed' : activity.state === 'active' ? 'In progress' : 'Upcoming'}</small></li>)}</ol>
    </div>

    {error && <div className="career-inline-error">{error}</div>}

    <div className="growth-decision-grid">
      {plan.question ? <section className="next-question">
        <div className="growth-card-title"><span><MessageSquare size={20}/></span><div><h3>One useful question</h3><p>This helps us find more relevant opportunities for you.</p></div></div>
        <div className="question-body"><h4>{plan.question.question}</h4>
          {plan.question.options.length > 0 ? <div className="answer-options">{plan.question.options.map(option => <button className={selectedAnswer === option ? 'selected' : ''} disabled={answerBusy} onClick={() => setSelectedAnswer(option)} key={option}><i/>{option}</button>)}</div> : <div className="typed-answer"><input aria-label={plan.question.question} disabled={answerBusy} value={typedAnswer} onChange={event => setTypedAnswer(event.target.value)} placeholder={plan.question.placeholder || 'Type your answer'}/></div>}
          <button className="save-answer" disabled={answerBusy || !(selectedAnswer || typedAnswer.trim())} onClick={() => onAnswer(plan.question!, selectedAnswer || typedAnswer)}>{answerBusy ? 'Saving…' : 'Save and continue'}<ArrowUpRight size={16}/></button>
        </div>
      </section> : <section className="next-question resolved"><CheckCircle2 size={22}/><div><h3>One useful question</h3><p>I already have enough information for the next application.</p></div></section>}

      {plan.decision ? <section className="agent-decision"><div className="growth-card-title"><span><CircleDollarSign size={20}/></span><div><h3>Trade-off decision</h3><p>Help us balance quality and quantity for your search.</p></div></div><div className="decision-body"><h4>{plan.decision.prompt}</h4><div>{plan.decision.options.map((option, index) => <button disabled={answerBusy} key={option.value} onClick={() => onDecision(plan.decision!, option.value)}><i>{index === 0 ? <Target size={17}/> : index === 1 ? <CircleDollarSign size={17}/> : <ArrowUpRight size={17}/>}</i><span>{option.label}</span><p>{index === 0 ? 'Higher match quality, fewer results' : index === 1 ? 'Good mix of quality and quantity' : 'More opportunities, wider range'}</p>{option.impact_jobs > 0 && <small>~ +{option.impact_jobs} roles<b>per week</b></small>}</button>)}</div></div></section> : <section className="agent-decision resolved"><CheckCircle2 size={22}/><h3>Trade-off saved</h3><p>Your current search preference is ready.</p></section>}
    </div>

    {cvUpdate && <section className="cv-update"><CheckCircle2 size={18}/><div><b>Your factual CV update is ready.</b><p>{Object.entries(cvUpdate.added).map(([section, values]) => `${section}: ${values.join(', ')}`).join(' · ')}</p></div><a href={`${API_ORIGIN}${cvUpdate.pdf_url}`} target="_blank" rel="noreferrer">Open PDF <ExternalLink size={13}/></a></section>}

    <aside className="growth-context">
      <div className="context-heading"><div className="growth-card-title"><span><BarChart3 size={20}/></span><div><h3>Market signals</h3><p>Insights from the job market to guide your decisions.</p></div></div><button>View all signals <ArrowUpRight size={14}/></button></div>
      {plan.recommendations.length ? <div className="recommendation-list">{plan.recommendations.slice(0, 3).map((item, index) => <article key={item.id}><span>{index === 0 ? <ArrowUpRight size={19}/> : index === 1 ? <Sparkles size={19}/> : <BriefcaseBusiness size={19}/>}</span><div><h4>{item.title}</h4><p>{item.detail}</p><small><b>+{Math.max(1, item.impact_jobs)}%</b> Based on current job postings</small></div></article>)}</div> : <p className="no-signal">No repeated skill gap was strong enough to recommend. That is a useful result too.</p>}
    </aside>

    {plan.exposure.suggested && <section className="growth-event"><span><GraduationCap size={20}/></span><div><b>Growth opportunity</b><p>{plan.exposure.reason}</p></div><button disabled={researchLoading} onClick={onResearch}>{researchLoading ? 'Searching…' : 'View event'}<ArrowUpRight size={14}/></button></section>}
    {research && <section className="research-results"><div className="research-result-head"><b>{research.message}</b><a href={research.search_url} target="_blank" rel="noreferrer">Full search <ExternalLink size={12}/></a></div>{research.items.map(item => <a href={item.url} target="_blank" rel="noreferrer" key={item.url}><span>{item.type}</span><b>{item.title}</b><p>{item.snippet}</p></a>)}</section>}
  </section>
}

function OutreachModal({ context, profile, onClose }: { context: OutreachContext; profile: Record<string, unknown>; onClose: () => void }) {
  const [contacts, setContacts] = useState<OutreachLead[]>([])
  const [searchUrl, setSearchUrl] = useState('')
  const [sourceNote, setSourceNote] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [loading, setLoading] = useState(true)
  const [drafting, setDrafting] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [draft, setDraft] = useState<{ subject: string; message: string; review_required: boolean; channel: string; mailto_url: string; profile_url: string; connection_required: boolean; instruction: string } | null>(null)
  const selected = contacts.find(contact => contact.id === selectedId) || null
  const emailDraftUrl = draft?.channel === 'email' && selected?.destination
    ? `mailto:${selected.destination}?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(draft.message)}`
    : draft?.mailto_url || ''

  useEffect(() => {
    let active = true
    async function discover() {
      try {
        const response = await fetch(`${API}/outreach/discover`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job: context.job, company_url: context.companyUrl }) })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'Could not find a published contact.')
        if (!active) return
        setContacts(data.contacts || [])
        setSelectedId(data.contacts?.[0]?.id || '')
        setSearchUrl(data.search_url || '')
        setSourceNote(data.source_note || '')
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'Could not find a published contact.')
      } finally {
        if (active) setLoading(false)
      }
    }
    void discover()
    return () => { active = false }
  }, [context.job.id, context.companyUrl])

  async function createDraft() {
    if (!selected) return
    setDrafting(true); setError(''); setCopied(false)
    try {
      const response = await fetch(`${API}/outreach/draft`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channel: selected.channel, lead: selected, job: context.job, profile, matched_skills: context.job.keywords }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not draft the message.')
      setDraft(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not draft the message.')
    } finally { setDrafting(false) }
  }

  async function copyDraft() {
    if (!draft) return
    await navigator.clipboard.writeText(draft.message)
    setCopied(true)
  }

  return <div className="modal-backdrop" onClick={onClose}>
    <section className="modal outreach-modal" onClick={event => event.stopPropagation()}>
      <button className="modal-close" aria-label="Close" onClick={onClose}><X size={17}/></button>
      <p className="eyebrow">REVIEW-FIRST OUTREACH</p>
      <h2>Find the right person, then write once.</h2>
      <p className="modal-company">{context.job.title} · {context.job.company}</p>
      {loading && <div className="outreach-loading"><RefreshCw className="spin" size={17}/> Checking published contacts and public profiles…</div>}
      {error && <p className="error">{error}</p>}
      {!loading && <>
        {contacts.length > 0 ? <div className="contact-list">{contacts.map(contact => <button className={selectedId === contact.id ? 'selected' : ''} key={contact.id} onClick={() => { setSelectedId(contact.id); setDraft(null) }}><span>{contact.channel === 'email' ? <Mail size={15}/> : <MessageSquare size={15}/>}</span><div><b>{contact.name}</b><small>{contact.role}</small></div><em>{contact.verified ? 'Published' : 'Check profile'}</em></button>)}</div> : <div className="no-contacts"><UserRoundSearch size={22}/><b>No contact was guessed.</b><p>No named profile or published recruiting email was clear enough.</p>{searchUrl && <a href={searchUrl} target="_blank" rel="noreferrer">Open the public search <ExternalLink size={13}/></a>}</div>}
        {selected && !draft && <button className="outreach-draft-button" disabled={drafting} onClick={createDraft}>{drafting ? <RefreshCw className="spin" size={15}/> : <MessageSquare size={15}/>} {drafting ? 'Writing from verified facts…' : `Draft for ${selected.name}`}</button>}
        {draft && <div className="outreach-draft">{draft.channel === 'email' && <label><span>Subject</span><input value={draft.subject} onChange={event => setDraft({ ...draft, subject: event.target.value })}/></label>}<label><span>Message</span><textarea value={draft.message} onChange={event => setDraft({ ...draft, message: event.target.value })}/></label><p><CheckCircle2 size={13}/>{draft.instruction}</p><div className="outreach-actions"><button onClick={copyDraft}>{copied ? <Check size={14}/> : <Copy size={14}/>} {copied ? 'Copied' : 'Copy message'}</button>{draft.channel === 'email' && emailDraftUrl && <a href={emailDraftUrl}>Open email draft <ArrowUpRight size={14}/></a>}{draft.channel === 'linkedin' && draft.profile_url && <a href={draft.profile_url} target="_blank" rel="noreferrer">Open profile <ArrowUpRight size={14}/></a>}</div></div>}
        {sourceNote && <small className="outreach-source">{sourceNote}</small>}
      </>}
    </section>
  </div>
}

function JobRow({ job, selected, saved, onSelect, onToggleSaved }: { job: Job; selected: boolean; saved: boolean; onSelect: () => void; onToggleSaved: () => void }) {
  const percent = Math.max(0, Math.min(100, Math.round(job.score * 100)))
  return <article className={`job-row ${selected ? 'selected' : ''}`}>
    <button className="job-row-main" onClick={onSelect} aria-current={selected ? 'true' : undefined}>
      <span className="company-monogram">{job.company.charAt(0).toUpperCase()}</span>
      <span className="job-row-copy"><h3>{job.title}</h3><b>{job.company}</b><small><MapPin size={12}/>{job.location}<i/> <BriefcaseBusiness size={12}/>{job.opportunity_type.replace('_', ' ')}</small></span>
      <span className="job-row-match"><b>{percent}%</b><small>Match</small></span>
      <span className={`row-status ${job.status}`}>{saved ? 'Saved' : job.status === 'ready' ? 'Ready' : 'Review first'}</span>
    </button>
    <button className={`row-save ${saved ? 'saved' : ''}`} aria-label={saved ? `Remove ${job.title} from saved` : `Save ${job.title}`} onClick={onToggleSaved}>{saved ? <BookmarkCheck size={16}/> : <Bookmark size={16}/>}</button>
  </article>
}

function JobInspector({ job, brief, loading, error, saved, onRetry, onToggleSaved, onPrepare, onApply, onOutreach }: { job: Job | null; brief?: JobBrief; loading: boolean; error?: string; saved: boolean; onRetry: () => void; onToggleSaved: () => void; onPrepare: (job: Job) => void; onApply: (job: Job, autoSubmit: boolean) => void; onOutreach: (job: Job, companyUrl: string) => void }) {
  const [tailoredCV, setTailoredCV] = useState<TailoredCV | null>(null)
  const [cvBusy, setCvBusy] = useState(false)
  const [cvError, setCvError] = useState('')
  const [moreOpen, setMoreOpen] = useState(false)

  if (!job) return <aside className="job-inspector empty-inspector"><BriefcaseBusiness size={24}/><p>Select a role to see the full brief.</p></aside>

  const matchPercent = Math.max(0, Math.min(100, Math.round(job.score * 100)))
  const listingUrl = brief?.listing_url || job.url
  const applicationJob = listingUrl === job.url ? job : { ...job, url: listingUrl }

  async function ensureTailoredCV(): Promise<TailoredCV> {
    if (tailoredCV) return tailoredCV
    if (!applicationJob.document_id) throw new Error('Run the search with a reusable CV first.')
    setCvBusy(true); setCvError('')
    try {
      const response = await fetch(`${API}/tailored-cv`, {
        credentials: 'include',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_id: applicationJob.document_id,
          title: applicationJob.title,
          company: applicationJob.company,
          description: applicationJob.description,
          url: applicationJob.url,
          keywords: applicationJob.keywords,
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
      onApply({ ...applicationJob, document_id: tailored.document_id }, autoSubmit)
    } catch { /* The inspector already shows the generation error. */ }
  }

  const factRows = brief ? [
    { label: job.opportunity_type === 'internship' ? 'Pay / stipend' : 'Salary', value: brief.facts.salary },
    { label: 'Work setup', value: brief.facts.work_mode },
    { label: 'Employment', value: brief.facts.employment_type },
    { label: 'Hours', value: brief.facts.schedule },
    ...(job.opportunity_type === 'internship' || brief.facts.duration ? [{ label: 'Duration', value: brief.facts.duration }] : []),
    { label: 'Experience', value: brief.facts.experience },
    ...(brief.facts.posted ? [{ label: 'Posted', value: brief.facts.posted }] : []),
    ...(brief.facts.deadline ? [{ label: 'Apply by', value: brief.facts.deadline }] : []),
  ] : []

  return <aside className="job-inspector" id="job-brief" aria-live="polite">
    <div className="inspector-head">
      <div className="inspector-title-row"><span className="inspector-monogram">{job.company.charAt(0).toUpperCase()}</span><div><h2>{job.title}</h2><b>{job.company}</b></div><span className="inspector-match"><i/>{matchPercent}% match</span></div>
      <div className="inspector-meta"><span><MapPin size={14}/>{brief?.facts.location || job.location}</span><span><BriefcaseBusiness size={14}/>{brief?.facts.employment_type || job.opportunity_type.replace('_', ' ')}</span>{brief?.company.industry && <span><Building2 size={14}/>{brief.company.industry}</span>}{brief?.facts.salary && <span><CircleDollarSign size={14}/>{brief.facts.salary}</span>}</div>
      <div className="inspector-actions">
        {saved && job.direct_listing ? <button className="primary-action" disabled={cvBusy} onClick={downloadTailoredCV}><Download size={17}/>{cvBusy ? 'Preparing your CV...' : 'Download tailored CV'}</button> : job.direct_listing ? <button className="primary-action" disabled={cvBusy} onClick={() => applyWithTailoredCV(false)}>{cvBusy ? 'Preparing your CV...' : 'Tailor CV & Apply'}<ArrowUpRight size={16}/></button> : <button className="primary-action" onClick={() => onApply(applicationJob, false)}>Open application<ArrowUpRight size={16}/></button>}
        {saved && job.direct_listing ? <button className="save-action" disabled={cvBusy} onClick={() => applyWithTailoredCV(false)}><FileText size={16}/>Autofill & review</button> : <button className={`save-action ${saved ? 'saved' : ''}`} onClick={onToggleSaved}>{saved ? <BookmarkCheck size={16}/> : <Bookmark size={16}/>}{saved ? 'Unsave' : 'Save'}</button>}
        {saved ? <button className="icon-action unsave-action" aria-label="Remove saved role" onClick={onToggleSaved}><Bookmark size={16}/>Unsave</button> : <button className="icon-action" aria-label="More actions" onClick={() => setMoreOpen(value => !value)}><MoreHorizontal size={18}/></button>}
        {moreOpen && <div className="inspector-more"><button onClick={() => onPrepare(applicationJob)}>Draft note</button><button onClick={() => onOutreach(applicationJob, brief?.company.url || '')}>Find a person</button>{job.direct_listing && <button onClick={downloadTailoredCV}>Download CV</button>}</div>}
      </div>
    </div>

    {loading && <div className="brief-loading"><div/><div/><div/><span>Reading the source listing and preparing your brief…</span></div>}
    {error && <div className="brief-error"><p>{error}</p><button onClick={onRetry}><RefreshCw size={14}/> Try again</button></div>}
    {brief && <div className="brief-content">
      <section className="brief-intro"><h3>About the role</h3><p>{brief.summary}</p></section>
      <div className="inspector-detail-grid">
        <section><h3>Key facts</h3><dl className="fact-list">{factRows.slice(0, 5).map(item => <div className={!item.value ? 'missing' : ''} key={item.label}><CheckCircle2 size={14}/><dd>{item.value || 'Not stated'}</dd></div>)}</dl></section>
        <section><div className="section-heading"><h3>Matched skills</h3><span>View all</span></div><div className="skill-line">{job.keywords.slice(0, 6).map(keyword => <span key={keyword}>{keyword}</span>)}</div></section>
      </div>
      <div className="inspector-info-grid">
        <article><span><CheckCircle2 size={20}/></span><div><b>Source quality</b><strong>{brief.quality === 'limited' ? 'Review source' : 'High confidence'}</strong><small>{brief.source_note}</small></div></article>
        <a href={listingUrl} target="_blank" rel="noreferrer"><span><ExternalLink size={20}/></span><div><b>Original listing</b><strong>View on {job.company} Careers</strong><small>opens in a new tab</small></div></a>
      </div>
    </div>}

    {cvError && <p className="cv-card-error">{cvError}</p>}
  </aside>
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
        const response = await fetch(`${API}/cv/readiness`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers }) })
        if (response.ok) setReadiness(await response.json())
      } catch { /* The final generation request remains authoritative. */ }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [answers])

  async function build() {
    setBuilding(true); setError('')
    try {
      const response = await fetch(`${API}/build-cv`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers }) })
      const data = await response.json()
      if (!response.ok) {
        if (data.detail?.readiness) setReadiness(data.detail.readiness)
        throw new Error(data.detail?.message || data.detail || 'Could not build the CV')
      }
      setResult({ text: data.cv_text, documentId: data.document_id, pdfUrl: data.pdf_url })
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not build the CV') }
    finally { setBuilding(false) }
  }

  if (result) return <div className="modal-backdrop"><section className="modal cv-result" role="dialog" aria-modal="true" aria-label="ATS CV ready"><button className="close" aria-label="Close CV builder" onClick={onClose}><X size={18}/></button><p className="eyebrow">ATS PDF READY</p><h2>Your CV is ready to review.</h2><p className="modal-company">Only facts from your answers were used.</p><textarea value={result.text} readOnly/><div className="modal-actions"><a className="draft-button" href={`${API_ORIGIN}${result.pdfUrl}`} download><Download size={15}/> Download PDF</a><button className="apply-button" onClick={() => onUse(result)}>Use for search <ArrowUpRight size={16}/></button></div></section></div>

  return <div className="modal-backdrop"><section className="modal cv-builder" role="dialog" aria-modal="true" aria-label="ATS CV builder"><button className="close" aria-label="Close CV builder" onClick={onClose}><X size={18}/></button><div className="readiness"><span style={{ width: `${readiness.progress}%` }}/></div><p className="eyebrow">CV BUILDER · {current.label} · {readiness.progress}% VERIFIED</p><h2>{current.question}</h2><p className="modal-company">{current.hint}</p><textarea autoFocus value={answers[current.key] ?? ''} onChange={event => setAnswers({ ...answers, [current.key]: event.target.value })} placeholder="Write factual information here..."/><div className="modal-actions"><button className="draft-button" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>Back</button>{step < CV_QUESTIONS.length - 1 ? <button className="apply-button" onClick={() => setStep(step + 1)}>Next <ArrowUpRight size={16}/></button> : <button className="apply-button" onClick={build} disabled={building || readiness.progress < 100}>{building ? 'Building ATS PDF...' : 'Generate ATS PDF'} <Sparkles size={16}/></button>}</div>{readiness.missing.length > 0 && step === CV_QUESTIONS.length - 1 && <ul className="missing-list">{readiness.missing.map(item => <li key={item.field}>{item.message}</li>)}</ul>}{error && <p className="error">{error}</p>}</section></div>
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
      const response = await fetch(`${API}/model-settings/models`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: settings.provider, base_url: settings.base_url, api_key: apiKey || undefined }) })
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
      const response = await fetch(`${API}/model-settings`, { method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...settings, api_key: apiKey || undefined }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not save settings')
      onSaved(data)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save settings') }
    finally { setBusy(false) }
  }
  return <div className="modal-backdrop"><section className="modal settings-modal" role="dialog" aria-modal="true" aria-label="Model settings"><button className="close" aria-label="Close model settings" onClick={onClose}><X size={18}/></button><p className="eyebrow">OLLAMA MODEL SETTINGS</p><h2>Choose local or cloud inference.</h2><div className="provider-tabs"><button className={settings.provider === 'ollama_local' ? 'selected' : ''} onClick={() => switchProvider('ollama_local')}>Local</button><button className={settings.provider === 'ollama_cloud' ? 'selected' : ''} onClick={() => switchProvider('ollama_cloud')}>Cloud</button></div><label className="modal-field"><span>Base URL</span><input value={settings.base_url} onChange={event => setSettings({ ...settings, base_url: event.target.value })}/></label>{settings.provider === 'ollama_cloud' && <label className="modal-field"><span>API key {settings.api_key_configured && '(already configured)'}</span><input type="password" value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder={settings.api_key_configured ? 'Leave blank to keep current key' : 'Required for Ollama Cloud'}/></label>}<div className="model-picker"><button className="draft-button" onClick={refresh} disabled={busy}><RefreshCw size={14}/>{busy ? 'Refreshing...' : 'Refresh models'}</button><select value={settings.model} onChange={event => setSettings({ ...settings, model: event.target.value })}><option value="">Choose a model</option>{models.map(model => <option value={model.name} key={model.name}>{model.name}{model.parameter_size ? ` · ${model.parameter_size}` : ''}</option>)}{settings.model && !models.some(model => model.name === settings.model) && <option value={settings.model}>{settings.model}</option>}</select></div>{error && <p className="error">{error}</p>}<button className="apply-button save-settings" onClick={save} disabled={busy || !settings.model}>Save model</button><small>Local Ollama needs no API key. Cloud keys stay in backend memory and are not written to the settings file.</small></section></div>
}

function ApplicationModal({ initial, onClose, onUnavailable, onAnswersSaved }: { initial: ApplicationSession; onClose: () => void; onUnavailable: () => void; onAnswersSaved: (values: Record<string, string>) => void }) {
  const [session, setSession] = useState(initial)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [automationError, setAutomationError] = useState('')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [commandBusy, setCommandBusy] = useState(false)
  const missing = session.details.missing_required ?? []

  useEffect(() => {
    if (['submitted', 'closed', 'failed', 'expired', 'unavailable'].includes(session.status)) return
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API}/application-sessions/${session.id}`, { credentials: 'include' })
        if (!response.ok) throw new Error('Could not refresh the application status.')
        setSession(await response.json())
        setAutomationError('')
      } catch (err) {
        setAutomationError(err instanceof Error ? err.message : 'Could not refresh the application status.')
      }
    }, 1200)
    return () => window.clearInterval(timer)
  }, [session.id, session.status])
  useEffect(() => {
    if (session.status === 'unavailable') onUnavailable()
  }, [session.status])
  useEffect(() => {
    setQuestionIndex(current => Math.min(current, Math.max(0, missing.length - 1)))
  }, [missing.length])

  async function command(value: 'submit' | 'retry' | 'close', values: Record<string, string> = {}) {
    if (commandBusy) return
    setCommandBusy(true)
    setAutomationError('')
    try {
      let approvalId = ''
      if (value === 'submit') {
        if (!session.application_id) throw new Error('This session is not linked to an application record.')
        if (!window.confirm('Review the employer form in the visible browser. Submit this application now?')) return
        const approvalResponse = await fetch(`${API}/agent/approvals`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action_type: 'submit_application', summary: 'Submit the reviewed employer application', target_type: 'application', target_id: session.application_id, payload: { session_id: session.id } }) })
        const approval = await approvalResponse.json()
        if (!approvalResponse.ok) throw new Error(approval.detail || 'Could not create submission approval.')
        const decisionResponse = await fetch(`${API}/agent/approvals/${approval.id}/decision`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision: 'approved', channel: 'app' }) })
        const decision = await decisionResponse.json()
        if (!decisionResponse.ok) throw new Error(decision.detail || 'Could not approve submission.')
        approvalId = decision.id
      }
      const response = await fetch(`${API}/application-sessions/${session.id}/commands`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ command: value, values, approval_id: approvalId }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not update the application session.')
      setSession(data)
      if (value === 'close') onClose()
    } catch (err) {
      setAutomationError(err instanceof Error ? err.message : 'Could not update the application session.')
    } finally {
      setCommandBusy(false)
    }
  }
  function saveAndRetry() {
    const values = Object.fromEntries(Object.entries(answers).filter(([, value]) => value.trim()))
    onAnswersSaved(values)
    command('retry', values)
  }

  const answeredCount = missing.filter(item => answers[item.memory_key]?.trim()).length
  const allAnswered = missing.length > 0 && answeredCount === missing.length
  const currentQuestion = missing[questionIndex]
  const questionOptions = currentQuestion ? (currentQuestion.options?.length ? currentQuestion.options : currentQuestion.input_type === 'checkbox' ? ['Yes', 'No'] : []) : []
  const currentAnswered = currentQuestion ? Boolean(answers[currentQuestion.memory_key]?.trim()) : false

  const isReady = session.status === 'ready_to_submit'
  return <div className="modal-backdrop application-backdrop">
    <section className="modal application-modal" role="dialog" aria-modal="true" aria-labelledby="application-status">
      <button className="close" aria-label="Close application browser" disabled={commandBusy} onClick={() => command('close')}><X size={21}/></button>
      <div className="application-hero">
        <div className="application-brand"><span><Sparkles size={22}/></span><b>Application Assistant</b></div>
        <h2 id="application-status" aria-live="polite">{isReady ? 'All set to submit.' : session.message}</h2>
        <p>{isReady ? 'You’re in control. You can review everything below before submitting. We’ll handle the rest.' : 'We’re preparing the application and will pause if we need one useful detail from you.'}</p>
        <img src="/jobflow-assistant.svg" alt=""/>
      </div>
      <div className="application-body">
        <div className="application-progress" aria-label="Application progress">
          <span className="done"><i><Check size={18}/></i><b>Find job</b></span>
          <span className="done"><i><Check size={18}/></i><b>Fill application</b></span>
          <span className="done"><i><Check size={18}/></i><b>Review</b></span>
          <span className={isReady ? 'current' : ''}><i>{isReady ? <Check size={18}/> : '4'}</i><b>Ready to submit</b></span>
        </div>
        {isReady && <div className="application-ready-card"><span><Check size={28}/></span><div><b>Ready to submit</b><p>Everything looks good! You can now submit your application.</p></div></div>}
        <div className="application-summary">
          <span><i><FileText size={24}/></i><small>CV uploaded</small><b>{session.details.cv_uploaded ? 'Yes' : 'No'}</b></span>
          <span><i><LayoutList size={24}/></i><small>Fields filled</small><b>{session.details.filled_fields?.length || 0} / {session.details.filled_fields?.length || 0}</b></span>
          <span><i><RefreshCw size={24}/></i><small>Saved answers reused</small><b>{session.details.reused_answers?.length || 0}</b></span>
        </div>
        {isReady && <div className="application-success-note"><CheckCircle2 size={22}/><div><b>Missing question answered</b><p>We filled in your work authorization based on your saved profile.</p></div></div>}
        {isReady && <div className="application-warning-note"><AlertTriangle size={24}/><div><b>There might be one extra step</b><p>Some companies may show an additional step, like a CAPTCHA or a login screen.<br/>We’ll pause the flow for you to complete it, then continue automatically.</p></div></div>}
      {session.details.blockers?.map(item => <p className="error" key={item}>{item}</p>)}
      {session.details.unavailable?.map(item => <p className="error" key={item}>{item}</p>)}

      {currentQuestion && <div className="answer-step">
        <div className="answer-progress-copy"><span>Missing detail {questionIndex + 1} of {missing.length}</span><b>{answeredCount}/{missing.length} answered</b></div>
        <div className="answer-progress"><i style={{ width: `${(answeredCount / missing.length) * 100}%` }}/></div>
        <label className="modal-field" key={currentQuestion.field_id}>
          <span>{currentQuestion.question}</span>
          {questionOptions.length ? <select autoFocus value={answers[currentQuestion.memory_key] ?? ''} onChange={event => setAnswers({ ...answers, [currentQuestion.memory_key]: event.target.value })}><option value="">Choose an answer</option>{questionOptions.map(option => <option value={option} key={option}>{option}</option>)}</select> : <input autoFocus value={answers[currentQuestion.memory_key] ?? ''} onChange={event => setAnswers({ ...answers, [currentQuestion.memory_key]: event.target.value })} placeholder={`Answer for ${currentQuestion.label}`}/>}
        </label>
        <div className="question-navigation"><button disabled={questionIndex === 0} onClick={() => setQuestionIndex(index => index - 1)}>Back</button><button disabled={!currentAnswered || questionIndex === missing.length - 1} onClick={() => setQuestionIndex(index => index + 1)}>Next <ArrowUpRight size={14}/></button></div>
      </div>}

        {automationError && <p className="error">{automationError}</p>}
        <div className="modal-actions application-actions">
        {isReady && <button className="draft-button application-review"><FileText size={17}/>Review answers</button>}
        <button className="draft-button" disabled={commandBusy} onClick={() => command('close')}><X size={17}/>{commandBusy ? 'Closing...' : 'Close browser'}</button>
        {isReady && <button className="auto-submit-button" disabled={commandBusy} onClick={() => command('submit')}>{commandBusy ? 'Submitting...' : 'Confirm submit'}<ArrowUpRight size={18}/></button>}
        {session.status === 'needs_input' && <button className="auto-submit-button" disabled={!allAnswered || commandBusy} onClick={saveAndRetry}><RefreshCw size={14}/>{commandBusy ? 'Continuing...' : 'Save answers & continue'}</button>}
        {['blocked', 'needs_review'].includes(session.status) && <button className="auto-submit-button" disabled={commandBusy} onClick={() => command('retry')}><RefreshCw size={14}/>{commandBusy ? 'Retrying...' : 'Retry after review'}</button>}
        {session.status === 'recoverable' && <button className="auto-submit-button" disabled={commandBusy} onClick={() => command('retry')}><RefreshCw size={14}/>{commandBusy ? 'Restoring...' : 'Resume saved session'}</button>}
        </div>
      </div>
    </section>
  </div>
}

function DraftModal({ draft, onClose }: { draft: { job: Job; text: string }; onClose: () => void }) { return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label="Application draft"><button className="close" aria-label="Close application draft" onClick={onClose}><X size={18}/></button><p className="eyebrow">APPLICATION DRAFT</p><h2>{draft.job.title}</h2><p className="modal-company">{draft.job.company}</p><textarea value={draft.text} readOnly/><div className="modal-actions"><button className="draft-button" onClick={() => navigator.clipboard.writeText(draft.text)}>Copy draft</button><button className="apply-button" onClick={() => window.open(draft.job.url, '_blank', 'noopener,noreferrer')}>Open listing <ArrowUpRight size={16}/></button></div></section></div> }

export default App
