import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight, Bot, CalendarClock, Check, CheckCircle2, ChevronRight, CircleDollarSign,
  Clock3, FileCheck2, Inbox, Languages, Mail, MessageSquare, Mic, MicOff, Pause,
  Play, Plus, RefreshCw, Send, ShieldCheck, Sparkles, Target, TimerReset, UserRound,
  UploadCloud, Volume2, X,
} from 'lucide-react'
import { api, API, Approval, DevelopmentPlan, Interview, InterviewEvaluation, NextAction, Offer, TrackedApplication } from './employment-api'
import { useI18n } from './i18n'
import './employment.css'

const APPLICATION_STAGES = [
  { key: 'prepare', label: 'Prepare', states: ['discovered', 'saved', 'preparing', 'ready_to_apply', 'applying', 'needs_input', 'ready_to_submit', 'blocked'] },
  { key: 'applied', label: 'Applied', states: ['applied', 'recruiter_reply', 'screening', 'on_hold'] },
  { key: 'interview', label: 'Interview', states: ['interview', 'final_interview'] },
  { key: 'decision', label: 'Decision', states: ['offer', 'accepted', 'rejected', 'withdrawn', 'closed', 'failed', 'expired'] },
]

const STATUS_LABEL: Record<string, string> = {
  ready_to_apply: 'Ready to apply', needs_input: 'Needs input', ready_to_submit: 'Ready to submit',
  recruiter_reply: 'Recruiter replied', final_interview: 'Final interview', on_hold: 'On hold',
}

const INTERVIEW_MODE_LABELS: Record<string, { en: string; ar: string }> = {
  hr: { en: 'HR interview', ar: 'مقابلة الموارد البشرية' },
  behavioral: { en: 'Behavioral interview', ar: 'مقابلة سلوكية' },
  technical: { en: 'Technical interview', ar: 'مقابلة تقنية' },
  case: { en: 'Case study', ar: 'دراسة حالة' },
  final: { en: 'Final interview', ar: 'المقابلة النهائية' },
}

const PAY_PERIOD_LABELS: Record<string, { en: string; ar: string }> = {
  monthly: { en: 'Monthly', ar: 'شهري' },
  annual: { en: 'Annual', ar: 'سنوي' },
  hourly: { en: 'Hourly', ar: 'بالساعة' },
}

function localizedLabel(labels: Record<string, { en: string; ar: string }>, value: string, locale: 'en' | 'ar') {
  return labels[value]?.[locale] || value.replaceAll('_', ' ')
}

function providerLabel(provider: string, locale: 'en' | 'ar') {
  const labels: Record<string, { en: string; ar: string }> = {
    gmail: { en: 'Gmail', ar: 'جيميل' },
    outlook: { en: 'Outlook', ar: 'أوتلوك' },
    google_calendar: { en: 'Google Calendar', ar: 'تقويم جوجل' },
    outlook_calendar: { en: 'Outlook Calendar', ar: 'تقويم أوتلوك' },
    telegram: { en: 'Telegram', ar: 'تليجرام' },
  }
  return labels[provider]?.[locale] || provider.replaceAll('_', ' ')
}

function LoadingLine({ label = 'Loading workspace…' }: { label?: string }) {
  return <div className="os-loading"><RefreshCw className="spin" size={16}/><span>{label}</span></div>
}

function EmptyBlock({ icon, title, copy, action }: { icon: React.ReactNode; title: string; copy: string; action?: React.ReactNode }) {
  return <div className="os-empty">{icon}<h3>{title}</h3><p>{copy}</p>{action}</div>
}

export function TodayPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const queryClient = useQueryClient()
  const actions = useQuery({ queryKey: ['actions'], queryFn: () => api<{ items: NextAction[] }>('/agent/actions') })
  const approvals = useQuery({ queryKey: ['approvals'], queryFn: () => api<{ items: Approval[] }>('/agent/approvals') })
  const analytics = useQuery({ queryKey: ['analytics'], queryFn: () => api<{ counts: Record<string, number>; rates: Record<string, number>; bottleneck: string; sample_note: string }>('/analytics') })
  const development = useQuery({ queryKey: ['development-plan'], queryFn: () => api<DevelopmentPlan>('/development/tasks') })
  const actionMutation = useMutation({
    mutationFn: ({ id, command }: { id: string; command: string }) => api(`/agent/actions/${id}`, { method: 'POST', body: JSON.stringify({ command }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['actions'] }),
  })
  const approvalMutation = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: string }) => api(`/agent/approvals/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision, channel: 'app' }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['approvals'] }),
  })
  const feedbackMutation = useMutation({
    mutationFn: ({ id, rating }: { id: string; rating: string }) => api(`/agent/actions/${id}/feedback`, { method: 'POST', body: JSON.stringify({ rating }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['actions'] }),
  })
  const allActions = actions.data?.items ?? []
  const primary = allActions[0]
  const qualificationTask = development.data?.items.find(item => !['completed', 'skipped', 'snoozed'].includes(item.status))
  const showQualification = Boolean(qualificationTask && (!primary || qualificationTask.priority >= primary.priority))
  const metrics = analytics.data
  const isLoading = actions.isLoading || approvals.isLoading || analytics.isLoading || development.isLoading

  return <section className="os-page os-today">
    {isLoading && <LoadingLine label="Building today's priorities…"/>}
    <div className="today-lead">
      <div className="agent-presence"><Bot size={18}/><span>Employment agent</span><i>Evidence-led</i></div>
      {showQualification && qualificationTask ? <>
        <p className="os-kicker">YOUR STEP TODAY · QUALIFICATION</p>
        <h2>{qualificationTask.title}</h2>
        <p className="today-copy">{qualificationTask.detail}</p>
        <div className="today-actions"><button className="os-primary" onClick={() => onNavigate('development')}>Open task <ArrowRight size={16}/></button></div>
        <p className="evidence-line"><ShieldCheck size={13}/>{Math.round((qualificationTask.market_evidence.frequency || 0) * 100)}% market frequency · +{qualificationTask.readiness_impact}% possible readiness coverage</p>
      </> : primary ? <>
        <p className="os-kicker">NEXT BEST ACTION</p>
        <h2>{primary.title}</h2>
        <p className="today-copy">{primary.detail}</p>
        <div className="today-actions">
          <button className="os-primary" onClick={() => primary.application_id ? onNavigate('applications') : actionMutation.mutate({ id: primary.id, command: 'done' })}>Open task <ArrowRight size={16}/></button>
          <button className="os-secondary" onClick={() => actionMutation.mutate({ id: primary.id, command: 'snooze' })}><TimerReset size={15}/> Snooze</button>
          <button className="os-quiet" onClick={() => actionMutation.mutate({ id: primary.id, command: 'done' })}><Check size={15}/> Mark done</button>
        </div>
        <p className="evidence-line"><ShieldCheck size={13}/>{Math.round(primary.confidence * 100)}% confidence · based on the recorded application state</p>
        <div className="recommendation-feedback" aria-label="Recommendation feedback"><span>Was this useful?</span><button onClick={() => feedbackMutation.mutate({ id: primary.id, rating: 'useful' })}>Useful</button><button onClick={() => feedbackMutation.mutate({ id: primary.id, rating: 'wrong' })}>Wrong</button><button onClick={() => feedbackMutation.mutate({ id: primary.id, rating: 'already_done' })}>Already done</button><button onClick={() => feedbackMutation.mutate({ id: primary.id, rating: 'not_relevant' })}>Not relevant</button></div>
      </> : <EmptyBlock icon={<Target size={28}/>} title="Choose the role you want to reach." copy="Start with a readiness diagnosis, then Wazzefni will choose one useful qualification or application move." action={<button className="os-primary" onClick={() => onNavigate('readiness')}>Diagnose readiness</button>}/>}
    </div>

    <div className="today-grid">
      <div className="today-queue">
        <div className="os-section-head"><div><p className="os-kicker">QUEUE</p><h3>After the first move</h3></div><span>{Math.max(0, allActions.length - 1)} pending</span></div>
        <div className="action-list">{allActions.slice(1).map(action => <article key={action.id} className="action-row">
          <span className={`impact-dot ${action.impact}`}/><div><b>{action.title}</b><p>{action.detail}</p></div><button aria-label="Mark done" onClick={() => actionMutation.mutate({ id: action.id, command: 'done' })}><Check size={15}/></button>
        </article>)}</div>
        {!allActions.length && !isLoading && <p className="muted-copy">The queue updates from real application events, not generic career advice.</p>}
      </div>

      <aside className="today-context">
        <div className="os-section-head"><div><p className="os-kicker">FUNNEL</p><h3>What is converting</h3></div></div>
        <div className="funnel-line">
          {['applied', 'replies', 'interviews', 'offers'].map((key, index) => <div key={key}><b>{metrics?.counts[key] ?? 0}</b><span>{key}</span>{index < 3 && <i/>}</div>)}
        </div>
        <p className="bottleneck-copy">{metrics?.bottleneck}</p>
        <button className="os-text-button" onClick={() => onNavigate('applications')}>Open application pipeline <ChevronRight size={14}/></button>

        {(approvals.data?.items.length ?? 0) > 0 && <div className="approval-stack">
          <p className="os-kicker">NEEDS YOUR APPROVAL</p>
          {approvals.data!.items.map(item => <article key={item.id}><ShieldCheck size={17}/><div><b>{item.summary}</b><small>{item.action_type.replaceAll('_', ' ')}</small></div><button onClick={() => approvalMutation.mutate({ id: item.id, decision: 'approved' })}>Approve</button><button className="reject" onClick={() => approvalMutation.mutate({ id: item.id, decision: 'rejected' })}><X size={14}/></button></article>)}
        </div>}
      </aside>
    </div>
  </section>
}

export function ApplicationsPage() {
  const queryClient = useQueryClient()
  const applications = useQuery({ queryKey: ['applications'], queryFn: () => api<{ items: TrackedApplication[] }>('/applications') })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const transition = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api(`/applications/${id}/transition`, { method: 'POST', body: JSON.stringify({ status, source: 'user', message: `Status changed to ${status}.` }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['applications'] }),
  })
  const followUp = useMutation({
    mutationFn: (id: string) => api<{ draft: { subject: string; body: string }; approval: Approval }>('/communications/follow-up', { method: 'POST', body: JSON.stringify({ application_id: id, language: document.documentElement.lang === 'ar' ? 'ar' : 'en' }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['approvals'] }),
  })
  const rows = applications.data?.items ?? []
  const selected = rows.find(item => item.id === selectedId) ?? rows[0]
  useEffect(() => { if (!selectedId && rows[0]) setSelectedId(rows[0].id) }, [rows, selectedId])

  if (applications.isLoading) return <LoadingLine label="Loading application history…"/>
  if (!rows.length) return <EmptyBlock icon={<Inbox size={29}/>} title="No applications tracked yet." copy="Start an application from Opportunities. Wazzefni will preserve every status, CV, answer, and outcome here."/>

  return <section className="os-page pipeline-page">
    <div className="pipeline-board">
      {APPLICATION_STAGES.map(stage => <section className="pipeline-column" key={stage.key}>
        <header><b>{stage.label}</b><span>{rows.filter(item => stage.states.includes(item.status)).length}</span></header>
        <div>{rows.filter(item => stage.states.includes(item.status)).map(item => <button className={`pipeline-item ${selected?.id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => setSelectedId(item.id)}>
          <span>{STATUS_LABEL[item.status] || item.status.replaceAll('_', ' ')}</span><b>{item.title}</b><small>{item.company || 'Company not stated'} · {item.location || 'Location not stated'}</small><i>{Math.round(item.match_score * 100)}% match</i>
        </button>)}</div>
      </section>)}
    </div>
    {selected && <aside className="pipeline-inspector">
      <p className="os-kicker">APPLICATION RECORD</p><h2>{selected.title}</h2><p>{selected.company} · {selected.location || 'Location not stated'}</p>
      <label className="os-field"><span>Current status</span><select value={selected.status} disabled={transition.isPending} onChange={event => transition.mutate({ id: selected.id, status: event.target.value })}>{APPLICATION_STAGES.flatMap(item => item.states).map(status => <option key={status} value={status}>{STATUS_LABEL[status] || status.replaceAll('_', ' ')}</option>)}</select></label>
      <div className="inspector-commands"><button className="os-primary" onClick={() => followUp.mutate(selected.id)} disabled={followUp.isPending}><Mail size={15}/>{followUp.isPending ? 'Drafting…' : 'Draft follow-up'}</button>{selected.url && <a className="os-secondary" href={selected.url} target="_blank" rel="noreferrer">Open listing</a>}</div>
      {followUp.data && <div className="draft-preview"><p className="os-kicker">REVIEW BEFORE SENDING</p><b>{followUp.data.draft.subject}</b><p>{followUp.data.draft.body}</p><small><ShieldCheck size={12}/>A pending approval was created. Nothing was sent.</small></div>}
      <div className="timeline"><p className="os-kicker">TIMELINE</p>{[...selected.events].reverse().map(event => <div key={event.id}><i/><span><b>{STATUS_LABEL[event.to_status] || event.to_status.replaceAll('_', ' ')}</b><small>{event.message || event.source} · {new Date(event.created_at).toLocaleString()}</small></span></div>)}</div>
    </aside>}
  </section>
}

export function InterviewsPage() {
  const { locale } = useI18n()
  const queryClient = useQueryClient()
  const interviews = useQuery({ queryKey: ['interviews'], queryFn: () => api<{ items: Interview[] }>('/interviews') })
  const applications = useQuery({ queryKey: ['applications'], queryFn: () => api<{ items: TrackedApplication[] }>('/applications') })
  const [activeId, setActiveId] = useState<string | null>(null)
  const activeQuery = useQuery({ queryKey: ['interview', activeId], queryFn: () => api<Interview>(`/interviews/${activeId}`), enabled: Boolean(activeId) })
  const [applicationId, setApplicationId] = useState('')
  const [mode, setMode] = useState('behavioral')
  const language = locale
  const [answer, setAnswer] = useState('')
  const [recording, setRecording] = useState(false)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])

  const create = useMutation({
    mutationFn: async () => {
      const app = applications.data?.items.find(item => item.id === applicationId)
      return api<Interview>('/interviews', { method: 'POST', body: JSON.stringify({ application_id: applicationId || null, title: app?.title || 'Target role', company: app?.company || '', description: String(app?.payload?.description || ''), profile: {}, mode, language }) })
    },
    onSuccess: item => { queryClient.invalidateQueries({ queryKey: ['interviews'] }); setActiveId(item.id) },
  })
  const submit = useMutation({
    mutationFn: ({ question, duration }: { question: string; duration: number }) => api(`/interviews/${activeId}/turns`, { method: 'POST', body: JSON.stringify({ question, answer, duration_seconds: duration, transcript_source: recording ? 'voice' : 'text', evidence: {}, language }) }),
    onSuccess: () => { setAnswer(''); setStartedAt(null); queryClient.invalidateQueries({ queryKey: ['interview', activeId] }) },
  })
  const active = activeQuery.data
  const questions = active?.plan.questions ?? []
  const questionIndex = Math.min(active?.turns.length ?? 0, Math.max(0, questions.length - 1))
  const question = questions[questionIndex]
  const latest = active?.turns[active.turns.length - 1]?.evaluation

  async function toggleRecording() {
    if (recording && recorder.current) { recorder.current.stop(); setRecording(false); return }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    chunks.current = []
    const instance = new MediaRecorder(stream)
    recorder.current = instance
    instance.ondataavailable = event => chunks.current.push(event.data)
    instance.onstop = async () => {
      stream.getTracks().forEach(track => track.stop())
      const blob = new Blob(chunks.current, { type: instance.mimeType || 'audio/webm' })
      const form = new FormData(); form.append('audio', blob, 'answer.webm')
      try {
        const response = await fetch(`${API}/interviews/transcribe?language=${language}`, { method: 'POST', credentials: 'include', body: form })
        const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Transcription failed')
        setAnswer(data.text)
      } catch (error) { window.alert(error instanceof Error ? error.message : 'Transcription failed') }
    }
    setStartedAt(Date.now()); instance.start(); setRecording(true)
  }

  function speakQuestion() {
    if (!question || !('speechSynthesis' in window)) return
    speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(question); utterance.lang = language === 'ar' ? 'ar-EG' : 'en-US'; speechSynthesis.speak(utterance)
  }

  return <section className="os-page interview-page">
    <aside className="session-list"><div className="os-section-head"><div><p className="os-kicker">PRACTICE HISTORY</p><h3>Interview sessions</h3></div><button onClick={() => setActiveId(null)} aria-label={locale === 'ar' ? 'جلسة تدريب جديدة' : 'New practice session'}><Plus size={15}/></button></div>{interviews.data?.items.map(item => <button key={item.id} className={activeId === item.id ? 'selected' : ''} onClick={() => setActiveId(item.id)}><span>{localizedLabel(INTERVIEW_MODE_LABELS, item.mode, locale)}</span><b>{item.plan.summary || (locale === 'ar' ? 'جلسة تدريب' : 'Practice session')}</b><small>{new Date(item.created_at).toLocaleDateString(locale === 'ar' ? 'ar-EG' : 'en-US')}</small></button>)}</aside>
    <div className="interview-workspace">
      {!activeId ? <div className="interview-setup"><div className="interview-mark"><MessageSquare size={25}/></div><p className="os-kicker">NEW MOCK INTERVIEW</p><h2>Practice against the actual role.</h2><p>Questions use the selected application and confirmed evidence. Feedback never infers emotion or personality.</p>
        <label className="os-field"><span>Application</span><select value={applicationId} onChange={e => setApplicationId(e.target.value)}><option value="">General practice</option>{applications.data?.items.map(item => <option key={item.id} value={item.id}>{item.title} · {item.company}</option>)}</select></label>
        <div className="setup-row"><label className="os-field"><span>Interview type</span><select value={mode} onChange={e => setMode(e.target.value)}>{['hr', 'behavioral', 'technical', 'case', 'final'].map(item => <option key={item} value={item}>{localizedLabel(INTERVIEW_MODE_LABELS, item, locale)}</option>)}</select></label><label className="os-field"><span>Language</span><input value={locale === 'ar' ? 'العربية' : 'English'} readOnly/></label></div>
        <button className="os-primary" disabled={create.isPending} onClick={() => create.mutate()}><Sparkles size={16}/>{create.isPending ? 'Building plan…' : 'Build interview plan'}</button>{create.error && <p className="warning-copy">{create.error.message}</p>}
      </div> : activeQuery.isLoading ? <LoadingLine label="Opening interview session…"/> : active && <>
        <header className="interview-head"><div><p className="os-kicker">{localizedLabel(INTERVIEW_MODE_LABELS, active.mode, locale)} · {locale === 'ar' ? `السؤال ${Math.min(questionIndex + 1, questions.length)} من ${questions.length}` : `QUESTION ${Math.min(questionIndex + 1, questions.length)} OF ${questions.length}`}</p><h2>{question || 'Session complete'}</h2></div>{question && <button className="speak-button" onClick={speakQuestion}><Volume2 size={17}/> Read aloud</button>}</header>
        {question ? <div className="answer-workspace"><textarea value={answer} onFocus={() => !startedAt && setStartedAt(Date.now())} onChange={e => setAnswer(e.target.value)} placeholder={language === 'ar' ? 'اكتب إجابتك أو سجّلها صوتيًا…' : 'Type your answer or record it…'} dir={language === 'ar' ? 'rtl' : 'ltr'}/><div className="answer-controls"><button className={`record-button ${recording ? 'recording' : ''}`} onClick={toggleRecording}>{recording ? <MicOff size={16}/> : <Mic size={16}/>} {recording ? 'Stop recording' : 'Record answer'}</button><span>{answer.trim().split(/\s+/).filter(Boolean).length} words</span><button className="os-primary" disabled={!answer.trim() || submit.isPending} onClick={() => submit.mutate({ question, duration: startedAt ? (Date.now() - startedAt) / 1000 : 0 })}>{submit.isPending ? 'Evaluating…' : 'Submit answer'} <ArrowRight size={15}/></button></div></div> : <EmptyBlock icon={<CheckCircle2 size={30}/>} title="Practice complete." copy="Review the feedback below, then repeat the session to measure improvement."/>}
        {latest && <EvaluationPanel evaluation={latest}/>}
      </>}
    </div>
  </section>
}

function EvaluationPanel({ evaluation }: { evaluation: InterviewEvaluation }) {
  const { locale } = useI18n()
  const scoreLabels: Record<string, string> = locale === 'ar'
    ? { relevance: 'الصلة', evidence: 'الأدلة', structure: 'التنظيم', clarity: 'الوضوح', specificity: 'التحديد' }
    : {}
  return <section className="evaluation-panel"><div className="os-section-head"><div><p className="os-kicker">ANSWER FEEDBACK</p><h3>Specific improvements</h3></div></div><div className="score-line">{Object.entries(evaluation.scores || {}).map(([key, value]) => <div key={key}><span>{scoreLabels[key] || key.replaceAll('_', ' ')}</span><b>{value}</b><i><em style={{ width: `${value}%` }}/></i></div>)}</div><div className="feedback-columns"><div><b>Working well</b><ul>{evaluation.strengths?.map(item => <li key={item}>{item}</li>)}</ul></div><div><b>Improve next</b><ul>{evaluation.improvements?.map(item => <li key={item}>{item}</li>)}</ul></div></div>{evaluation.delivery && <p className="delivery-note"><TimerReset size={14}/>{locale === 'ar' ? `${evaluation.delivery.word_count} كلمة${evaluation.delivery.words_per_minute ? ` · ${evaluation.delivery.words_per_minute} كلمة/دقيقة` : ''} · ${evaluation.delivery.filler_word_count ?? 0} كلمات حشو` : `${evaluation.delivery.word_count} words${evaluation.delivery.words_per_minute ? ` · ${evaluation.delivery.words_per_minute} words/min` : ''} · ${evaluation.delivery.filler_word_count ?? 0} filler words`}</p>}<small>{evaluation.safety_note}</small></section>
}

export function OffersPage() {
  const { locale } = useI18n()
  const queryClient = useQueryClient()
  const offers = useQuery({ queryKey: ['offers'], queryFn: () => api<{ items: Offer[] }>('/offers') })
  const applications = useQuery({ queryKey: ['applications'], queryFn: () => api<{ items: TrackedApplication[] }>('/applications') })
  const [formOpen, setFormOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [comparison, setComparison] = useState<{ comparable: boolean; reason?: string; items: (Offer & { annual_base?: number })[]; source_note?: string } | null>(null)
  const [draft, setDraft] = useState<{ subject: string; body: string } | null>(null)
  const create = useMutation({ mutationFn: (payload: Record<string, unknown>) => api('/offers', { method: 'POST', body: JSON.stringify(payload) }), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['offers'] }); setFormOpen(false) } })
  const compare = useMutation({ mutationFn: () => api<typeof comparison>('/offers/compare', { method: 'POST', body: JSON.stringify({ offer_ids: selected }) }), onSuccess: data => setComparison(data) })
  const makeDraft = useMutation({ mutationFn: ({ id, purpose }: { id: string; purpose: string }) => api<{ draft: { subject: string; body: string } }>(`/offers/${id}/draft`, { method: 'POST', body: JSON.stringify({ purpose, language: document.documentElement.lang === 'ar' ? 'ar' : 'en' }) }), onSuccess: data => { setDraft(data.draft); queryClient.invalidateQueries({ queryKey: ['approvals'] }) } })
  const items = offers.data?.items ?? []

  return <section className="os-page offers-page"><div className="offers-head"><div><p className="os-kicker">DECISION WORKSPACE</p><h2>Compare the full offer, not just salary.</h2><p>Wazzefni keeps stated facts separate from assumptions and never sends a response without approval.</p></div><button className="os-primary" onClick={() => setFormOpen(true)}><Plus size={16}/> Add offer</button></div>
    {!items.length && !formOpen ? <EmptyBlock icon={<CircleDollarSign size={30}/>} title="No offers recorded yet." copy="When an offer arrives, capture its terms here to compare, clarify, and negotiate with evidence." action={<button className="os-secondary" onClick={() => setFormOpen(true)}>Record an offer</button>}/> : <div className="offer-list">{items.map(item => <article className={selected.includes(item.id) ? 'selected' : ''} key={item.id}><label><input type="checkbox" checked={selected.includes(item.id)} onChange={() => setSelected(current => current.includes(item.id) ? current.filter(id => id !== item.id) : [...current, item.id])}/><span>Compare</span></label><p className="os-kicker">{item.status}</p><h3>{item.title}</h3><p>{item.company}</p><b>{item.base_salary != null ? `${item.base_salary.toLocaleString()} ${item.currency} / ${localizedLabel(PAY_PERIOD_LABELS, item.pay_period, locale)}` : 'Compensation not stated'}</b><div><button onClick={() => makeDraft.mutate({ id: item.id, purpose: 'clarify' })}>Clarify</button><button onClick={() => makeDraft.mutate({ id: item.id, purpose: 'negotiate' })}>Negotiate</button></div></article>)}</div>}
    {selected.length >= 2 && <button className="compare-bar" disabled={compare.isPending} onClick={() => compare.mutate()}><CircleDollarSign size={17}/>{compare.isPending ? 'Comparing…' : locale === 'ar' ? `مقارنة ${selected.length} عروض` : `Compare ${selected.length} offers`}</button>}
    {comparison && <section className="comparison"><div className="os-section-head"><div><p className="os-kicker">SIDE-BY-SIDE</p><h3>{comparison.comparable ? 'Comparable stated terms' : 'Comparison needs one more fact'}</h3></div><button onClick={() => setComparison(null)}><X size={15}/></button></div>{comparison.reason && <p className="warning-copy">{comparison.reason}</p>}<div>{comparison.items.map(item => <article key={item.id}><b>{item.company}</b><span>{item.title}</span><strong>{item.annual_base ? `${item.annual_base.toLocaleString()} ${item.currency} / year` : 'Not comparable'}</strong>{Object.entries((item as any).non_monetary || {}).map(([key, value]) => <p key={key}><span>{key}</span>{String(value)}</p>)}</article>)}</div><small>{comparison.source_note}</small></section>}
    {draft && <section className="draft-sheet"><button onClick={() => setDraft(null)}><X size={16}/></button><p className="os-kicker">REVIEW BEFORE SENDING</p><h3>{draft.subject}</h3><textarea value={draft.body} onChange={e => setDraft({ ...draft, body: e.target.value })}/><p><ShieldCheck size={13}/>A pending approval was created. Nothing was sent automatically.</p></section>}
    {formOpen && <OfferForm applications={applications.data?.items ?? []} onClose={() => setFormOpen(false)} onSubmit={payload => create.mutate(payload)} busy={create.isPending}/>}
  </section>
}

function OfferForm({ applications, onClose, onSubmit, busy }: { applications: TrackedApplication[]; onClose: () => void; onSubmit: (payload: Record<string, unknown>) => void; busy: boolean }) {
  const { locale } = useI18n()
  const [applicationId, setApplicationId] = useState('')
  const [company, setCompany] = useState('')
  const [title, setTitle] = useState('')
  const [salary, setSalary] = useState('')
  const [currency, setCurrency] = useState('EGP')
  const [period, setPeriod] = useState('monthly')
  function submit(event: FormEvent) { event.preventDefault(); const app = applications.find(item => item.id === applicationId); onSubmit({ application_id: applicationId || null, company: company || app?.company, title: title || app?.title, base_salary: salary ? Number(salary) : null, currency, pay_period: period, details: {} }) }
  return <div className="os-backdrop"><form className="os-dialog" onSubmit={submit}><button type="button" className="dialog-close" onClick={onClose} aria-label={locale === 'ar' ? 'إغلاق' : 'Close'}><X size={16}/></button><p className="os-kicker">RECORD OFFER</p><h2>Capture only stated terms.</h2><label className="os-field"><span>Related application</span><select value={applicationId} onChange={e => { setApplicationId(e.target.value); const app = applications.find(item => item.id === e.target.value); if (app) { setCompany(app.company); setTitle(app.title) } }}><option value="">Choose application</option>{applications.map(item => <option key={item.id} value={item.id}>{item.title} · {item.company}</option>)}</select></label><label className="os-field"><span>Company</span><input required value={company} onChange={e => setCompany(e.target.value)}/></label><label className="os-field"><span>Role</span><input required value={title} onChange={e => setTitle(e.target.value)}/></label><div className="setup-row"><label className="os-field"><span>Base salary</span><input type="number" min="0" value={salary} onChange={e => setSalary(e.target.value)} placeholder="Not stated"/></label><label className="os-field"><span>Currency</span><select value={currency} onChange={e => setCurrency(e.target.value)}>{['EGP','SAR','AED','USD','EUR','GBP'].map(item => <option key={item}>{item}</option>)}</select></label><label className="os-field"><span>Period</span><select value={period} onChange={e => setPeriod(e.target.value)}>{['monthly','annual','hourly'].map(item => <option key={item} value={item}>{localizedLabel(PAY_PERIOD_LABELS, item, locale)}</option>)}</select></label></div><button className="os-primary" disabled={busy}>{busy ? 'Saving…' : 'Save offer'}</button></form></div>
}

type StoredDocument = {
  id: string; source_name: string; document_type: string; active: boolean; created_at: string; metadata: Record<string, unknown>
}

type ProfileQuestion = {
  memory_key: string; label: string; question: string; reason: string; input_type: string; options: string[]; contexts: string[]
  kind: 'confirm' | 'missing'; inferred_value: string; generated_by: 'llm' | 'fallback'; basis: 'explicit' | 'derived' | 'missing'
}

type ProfileCompleteness = {
  known: Record<string, { value: string; source: string }>; missing: ProfileQuestion[]
  completed: number; total: number; percent: number; context: string; cv_reviewed: boolean; analysis_source: 'llm' | 'fallback' | 'none'
}

export function ProfilePage() {
  const { locale, setLocale: setAppLocale } = useI18n()
  const queryClient = useQueryClient()
  const profile = useQuery({ queryKey: ['profile'], queryFn: () => api<{ locale: string; country: string; profile: Record<string, unknown>; preferences: Record<string, unknown>; facts: { id: string; fact_key: string; value: string; category: string; cv_safe: boolean }[]; updated_at?: string }>('/profile') })
  const documents = useQuery({ queryKey: ['documents'], queryFn: () => api<{ items: StoredDocument[] }>('/documents') })
  const integrations = useQuery({ queryKey: ['integrations'], queryFn: () => api<{ items: { provider: string; status: string; account_label: string; scopes: string[] }[] }>('/integrations') })
  const integrationReadiness = useQuery({ queryKey: ['integration-readiness'], queryFn: () => api<{ providers: Record<string, { configured: boolean }>; password_email: { configured: boolean } }>('/integrations/readiness') })
  const [factKey, setFactKey] = useState('')
  const [factValue, setFactValue] = useState('')
  const [telegramOpen, setTelegramOpen] = useState(false)
  const [botToken, setBotToken] = useState('')
  const [chatId, setChatId] = useState('')
  const [profileDraft, setProfileDraft] = useState({ name: '', phone: '', headline: '', location: '', bio: '' })
  const [cvMessage, setCvMessage] = useState<{ kind: 'uploaded' | 'activated'; name?: string } | null>(null)
  const update = useMutation({ mutationFn: (payload: Record<string, unknown>) => api('/profile', { method: 'PATCH', body: JSON.stringify(payload) }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['profile'] }) })
  const saveDetails = useMutation({ mutationFn: () => api('/profile', { method: 'PATCH', body: JSON.stringify({ profile: profileDraft }) }), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['profile'] }); queryClient.invalidateQueries({ queryKey: ['profile-completeness'] }) } })
  const addFact = useMutation({ mutationFn: () => api('/career-facts', { method: 'POST', body: JSON.stringify({ fact_key: factKey, value: factValue, category: 'profile', confirmed: true, cv_safe: false }) }), onSuccess: () => { setFactKey(''); setFactValue(''); queryClient.invalidateQueries({ queryKey: ['profile'] }) } })
  const uploadCV = useMutation({
    mutationFn: async (file: File) => { const body = new FormData(); body.append('cv', file); body.append('locale', locale); return api<{ document: StoredDocument; insights: Record<string, unknown> }>('/documents', { method: 'POST', body }) },
    onSuccess: data => {
      setCvMessage({ kind: 'uploaded', name: data.document.source_name })
      window.dispatchEvent(new CustomEvent('wazzefni:cv-insights', { detail: { document_id: data.document.id, ...data.insights } }))
      void Promise.all([queryClient.invalidateQueries({ queryKey: ['documents'] }), queryClient.invalidateQueries({ queryKey: ['profile'] }), queryClient.invalidateQueries({ queryKey: ['profile-completeness'] })])
    },
  })
  const activateCV = useMutation({
    mutationFn: (id: string) => api(`/documents/${id}/activate`, { method: 'POST' }),
    onSuccess: (_data, id) => {
      setCvMessage({ kind: 'activated' })
      void Promise.all([queryClient.invalidateQueries({ queryKey: ['documents'] }), queryClient.invalidateQueries({ queryKey: ['profile'] }), queryClient.invalidateQueries({ queryKey: ['profile-completeness'] })])
      void api<Record<string, unknown>>(`/documents/${id}/insights?locale=${locale}`)
        .then(review => window.dispatchEvent(new CustomEvent('wazzefni:cv-insights', { detail: review })))
        .catch(() => { /* The active CV remains selected; the user can retry AI review later. */ })
    },
  })
  const telegram = useMutation({ mutationFn: () => api('/integrations/telegram/configure', { method: 'POST', body: JSON.stringify({ bot_token: botToken, chat_id: chatId }) }), onSuccess: () => { setBotToken(''); setTelegramOpen(false); queryClient.invalidateQueries({ queryKey: ['integrations'] }) } })
  const syncMail = useMutation({ mutationFn: (provider: string) => api<{ ingested: number; transitioned: number; needs_review: number }>(`/integrations/${provider}/sync`, { method: 'POST' }), onSuccess: data => { queryClient.invalidateQueries({ queryKey: ['applications'] }); window.alert(locale === 'ar' ? `تمت مزامنة ${data.ingested} رسالة توظيف جديدة و${data.transitioned} تحديث لطلبات التقديم.` : `Synced ${data.ingested} new recruiting message(s); ${data.transitioned} application update(s).`) } })
  const data = profile.data
  useEffect(() => {
    const values = data?.profile || {}
    setProfileDraft({
      name: String(values.name || ''), phone: String(values.phone || ''), headline: String(values.headline || ''),
      location: String(values.location || ''), bio: String(values.bio || ''),
    })
  }, [data?.updated_at])
  function setLocale(next: string) { const normalized = next === 'ar' ? 'ar' : 'en'; setAppLocale(normalized); update.mutate({ locale: normalized }) }
  async function openDocument(id: string) {
    const response = await fetch(`${API}/documents/${id}.pdf`, { credentials: 'include' })
    if (!response.ok) throw new Error(locale === 'ar' ? 'تعذّر فتح الملف' : 'Could not open this file')
    const url = URL.createObjectURL(await response.blob())
    window.open(url, '_blank', 'noopener,noreferrer')
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  }
  async function reviewDocument(id: string) {
    try {
      const review = await api<Record<string, unknown>>(`/documents/${id}/insights?locale=${locale}`)
      window.dispatchEvent(new CustomEvent('wazzefni:cv-insights', { detail: review }))
    } catch (error) {
      window.alert(error instanceof Error ? error.message : locale === 'ar' ? 'تعذّرت مراجعة فهم السيرة.' : 'Could not review this CV understanding.')
    }
  }
  async function connectOAuth(provider: 'gmail' | 'outlook') {
    const redirectUri = `${window.location.origin}/profile`
    const result = await api<{ url: string }>(`/integrations/${provider}/oauth/start`, { method: 'POST', body: JSON.stringify({ redirect_uri: redirectUri }) })
    localStorage.setItem('wazzefni-oauth-provider', provider)
    window.location.href = result.url
  }
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code'); const state = params.get('state'); const provider = localStorage.getItem('wazzefni-oauth-provider') || localStorage.getItem('jobflow-oauth-provider')
    if (!code || !state || (provider !== 'gmail' && provider !== 'outlook')) return
    api(`/integrations/${provider}/oauth/callback`, { method: 'POST', body: JSON.stringify({ code, state, redirect_uri: `${window.location.origin}/profile` }) })
      .then(() => { localStorage.removeItem('wazzefni-oauth-provider'); localStorage.removeItem('jobflow-oauth-provider'); window.history.replaceState({}, '', '/profile'); queryClient.invalidateQueries({ queryKey: ['integrations'] }) })
      .catch(error => window.alert(error instanceof Error ? error.message : locale === 'ar' ? 'تعذّر ربط البريد الإلكتروني' : 'Could not connect email'))
  }, [queryClient])
  const profileValues = data?.profile || {}
  const hiddenProfileKeys = new Set([
    profileValues.name ? 'full_name' : '', profileValues.location ? 'preferred_location' : '',
    (profileValues.linkedin || profileValues.github) ? 'links' : '',
  ])
  const visibleProfile = Object.entries(profileValues).filter(([key, value]) => !hiddenProfileKeys.has(key) && value != null && String(value).trim())
  const visibleProfileKeys = new Set(visibleProfile.map(([key]) => key))
  if (visibleProfileKeys.has('name')) visibleProfileKeys.add('full_name')
  if (visibleProfileKeys.has('location')) visibleProfileKeys.add('preferred_location')
  const visibleFacts = (data?.facts || []).filter(fact => !visibleProfileKeys.has(fact.fact_key) && fact.fact_key !== 'links')
  const words = locale === 'ar' ? {
    kicker: 'بياناتي المهنية', title: 'بياناتك وسيرتك في مكان واحد.', copy: 'عدّل بياناتك أو غيّر سيرتك هنا. أي استنتاج من السيرة يفضل غير مؤكد لحد ما تراجعه بنفسك.', language: 'اللغة', market: 'السوق', saved: 'بياناتي', evidence: 'معلومات مؤكدة', documents: 'السيرة الذاتية', active: 'المستخدمة حاليًا', addName: 'اسم المعلومة، مثل مدة الإشعار', addValue: 'الإجابة المؤكدة', add: 'إضافة معلومة', workflow: 'التكاملات', workflowTitle: 'البريد والتقويم وتليجرام', notConnected: 'غير متصل', connected: 'متصل', connect: 'ربط', sync: 'مزامنة', update: 'تحديث', approval: 'موافقتك مطلوبة دائمًا', approvalCopy: 'لا يتم إرسال طلب أو بريد أو تعديل تقويم أو رد على عرض من دون موافقتك.', cvSafe: 'آمن للسيرة', downloaded: 'فتح', review: 'مراجعة الفهم', use: 'استخدام', upload: 'رفع سيرة جديدة', uploading: 'جارٍ الرفع والتحليل…', saveData: 'حفظ البيانات', savingData: 'جارٍ الحفظ…', name: 'الاسم', phone: 'رقم الهاتف', headline: 'المسمى المهني', location: 'الموقع', bio: 'نبذة قصيرة', emptyProfile: 'أكمل بياناتك وستظهر هنا تلقائيًا.'
  } : {
    kicker: 'MY CAREER DATA', title: 'Your data and CV, in one place.', copy: 'Edit your details or replace your CV here. Anything inferred from the CV stays unconfirmed until you review it.', language: 'Language', market: 'Market', saved: 'My details', evidence: 'Confirmed information', documents: 'CV', active: 'Active now', addName: 'Fact name, e.g. notice period', addValue: 'Confirmed answer', add: 'Add fact', workflow: 'CONNECTED WORKFLOW', workflowTitle: 'Email, calendar, and Telegram', notConnected: 'Not connected', connected: 'Connected', connect: 'Connect', sync: 'Sync', update: 'Update', approval: 'Human approval stays on', approvalCopy: 'Submission, sending, calendar changes, and offer responses cannot bypass the approval layer.', cvSafe: 'CV safe', downloaded: 'Open', review: 'Review understanding', use: 'Use', upload: 'Upload a new CV', uploading: 'Uploading and reviewing…', saveData: 'Save details', savingData: 'Saving…', name: 'Name', phone: 'Phone number', headline: 'Professional headline', location: 'Location', bio: 'Short bio', emptyProfile: 'Complete your profile and the saved fields will appear here.'
  }
  return <section className="os-page profile-page"><div className="profile-main"><p className="os-kicker">{words.kicker}</p><h2>{words.title}</h2><p>{words.copy}</p><div className="profile-settings"><label className="os-field"><span>{words.language}</span><select value={locale} onChange={e => setLocale(e.target.value)}><option value="en">English</option><option value="ar">العربية</option></select></label><label className="os-field"><span>{words.market}</span><select value={data?.country || 'EG'} onChange={e => update.mutate({ country: e.target.value })}><option value="EG">{locale === 'ar' ? 'مصر' : 'Egypt'}</option><option value="SA">{locale === 'ar' ? 'السعودية' : 'Saudi Arabia'}</option><option value="AE">{locale === 'ar' ? 'الإمارات' : 'United Arab Emirates'}</option></select></label></div>
    <section className="saved-profile-block"><div className="os-section-head"><div><p className="os-kicker">{words.saved}</p><h3>{locale === 'ar' ? 'عدّل بياناتك الأساسية' : 'Edit your core details'}</h3></div></div><form className="profile-data-form" onSubmit={event => { event.preventDefault(); saveDetails.mutate() }}><label className="os-field"><span>{words.name}</span><input value={profileDraft.name} onChange={event => setProfileDraft(current => ({ ...current, name: event.target.value }))}/></label><label className="os-field"><span>{words.phone}</span><input inputMode="tel" value={profileDraft.phone} onChange={event => setProfileDraft(current => ({ ...current, phone: event.target.value }))}/></label><label className="os-field"><span>{words.headline}</span><input value={profileDraft.headline} onChange={event => setProfileDraft(current => ({ ...current, headline: event.target.value }))}/></label><label className="os-field"><span>{words.location}</span><input value={profileDraft.location} onChange={event => setProfileDraft(current => ({ ...current, location: event.target.value }))}/></label><label className="os-field profile-bio"><span>{words.bio}</span><textarea rows={3} value={profileDraft.bio} onChange={event => setProfileDraft(current => ({ ...current, bio: event.target.value }))}/></label><div className="profile-data-save">{saveDetails.isSuccess && <span><Check size={14}/>{locale === 'ar' ? 'تم الحفظ' : 'Saved'}</span>}<button className="os-primary" disabled={saveDetails.isPending}>{saveDetails.isPending ? words.savingData : words.saveData}</button></div></form></section>
    <div className="fact-list-os"><div className="os-section-head"><div><p className="os-kicker">{locale === 'ar' ? 'حقائق مؤكدة ومحفوظة' : 'SAVED FACTS'}</p><h3>{words.evidence}</h3></div><span>{visibleFacts.length}</span></div>{visibleFacts.map(fact => <article key={fact.id}><CheckCircle2 size={16}/><div><b>{fact.fact_key.replaceAll('_', ' ')}</b><p>{fact.value}</p></div>{fact.cv_safe && <span>{words.cvSafe}</span>}</article>)}</div>
    <form className="fact-form" onSubmit={e => { e.preventDefault(); addFact.mutate() }}><input required value={factKey} onChange={e => setFactKey(e.target.value)} placeholder={words.addName}/><input required value={factValue} onChange={e => setFactValue(e.target.value)} placeholder={words.addValue}/><button disabled={addFact.isPending}><Plus size={15}/> {words.add}</button></form>
    <section className="document-list"><div className="os-section-head"><div><p className="os-kicker">{words.documents}</p><h3>{locale === 'ar' ? 'غيّر السيرة التي يستخدمها وظّفني' : 'Change the CV Wazzefni uses'}</h3></div><label className="cv-profile-upload"><UploadCloud size={15}/>{uploadCV.isPending ? words.uploading : words.upload}<input type="file" accept=".pdf,.txt" disabled={uploadCV.isPending} onChange={event => { const file = event.target.files?.[0]; if (file) uploadCV.mutate(file); event.currentTarget.value = '' }}/></label></div>{cvMessage && <p className="cv-profile-message"><Sparkles size={14}/>{locale === 'ar' ? (cvMessage.kind === 'uploaded' ? `تم رفع ${cvMessage.name} وتحليله. راجع الاستنتاجات للتأكيد.` : 'تم تغيير السيرة المستخدمة وتحليلها من جديد.') : (cvMessage.kind === 'uploaded' ? `${cvMessage.name} was uploaded and reviewed. Confirm any inferred details.` : 'The active CV was changed and reviewed again.')}</p>}{uploadCV.error && <p className="warning-copy">{uploadCV.error.message}</p>}{documents.data?.items.map(item => <article key={item.id}><span><FileCheck2 size={17}/></span><div><b>{item.source_name}</b><small>{new Date(item.created_at).toLocaleDateString(locale === 'ar' ? 'ar-EG' : 'en-US')}</small></div>{item.active && <i>{words.active}</i>}<div className="document-actions"><button type="button" onClick={() => void openDocument(item.id)}>{words.downloaded}</button><button type="button" onClick={() => void reviewDocument(item.id)}>{words.review}</button>{!item.active && <button type="button" disabled={activateCV.isPending} onClick={() => activateCV.mutate(item.id)}>{words.use}</button>}</div></article>)}</section>
  </div>
    <aside className="integration-panel"><p className="os-kicker">{words.workflow}</p><h3>{words.workflowTitle}</h3><p>{locale === 'ar' ? 'تُحفظ الرموز في مخزن مفاتيح نظام التشغيل، وتظل الإجراءات الخارجية تحت موافقتك.' : 'Tokens stay in the operating system keyring. External actions still require your approval.'}</p><div className="integration-list">{integrations.data?.items.map(item => { const configured = integrationReadiness.data?.providers[item.provider]?.configured !== false; return <article key={item.provider}><span>{item.provider.includes('calendar') ? <CalendarClock size={17}/> : item.provider === 'telegram' ? <Send size={17}/> : <Mail size={17}/>}</span><div><b>{providerLabel(item.provider, locale)}</b><small>{item.status === 'connected' ? item.account_label || words.connected : !configured ? (locale === 'ar' ? 'يحتاج مفاتيح الخدمة في الخادم' : 'Server credentials required') : words.notConnected}</small></div><i className={item.status}/>{item.provider === 'telegram' && <button onClick={() => setTelegramOpen(true)}>{item.status === 'connected' ? words.update : words.connect}</button>}{['gmail','outlook'].includes(item.provider) && <button disabled={!configured} title={!configured ? (locale === 'ar' ? 'أضف مفاتيح OAuth في إعدادات الخادم أولًا' : 'Add OAuth credentials to the server environment first') : ''} onClick={() => item.status === 'connected' ? syncMail.mutate(item.provider) : connectOAuth(item.provider as 'gmail'|'outlook')}>{item.status === 'connected' ? words.sync : !configured ? (locale === 'ar' ? 'يلزم إعداد الخادم' : 'Setup required') : words.connect}</button>}</article> })}</div>{integrationReadiness.data && !integrationReadiness.data.password_email.configured && <p className="integration-setup-note"><Mail size={14}/>{locale === 'ar' ? 'روابط استعادة كلمة المرور تعمل محليًا. أضف إعدادات SMTP لإرسالها بالبريد.' : 'Password-reset links work locally. Add SMTP settings to deliver them by email.'}</p>}<div className="privacy-note"><ShieldCheck size={18}/><div><b>{words.approval}</b><p>{words.approvalCopy}</p></div></div></aside>
    {telegramOpen && <div className="os-backdrop"><form className="os-dialog" onSubmit={e => { e.preventDefault(); telegram.mutate() }}><button type="button" className="dialog-close" aria-label={locale === 'ar' ? 'إغلاق' : 'Close'} onClick={() => setTelegramOpen(false)}><X size={16}/></button><p className="os-kicker">TELEGRAM CONTROL</p><h2>Connect your private bot.</h2><p>Use BotFather to create a bot, then provide the token and your chat ID. The token is stored in the OS keyring.</p><label className="os-field"><span>Bot token</span><input type="password" required value={botToken} onChange={e => setBotToken(e.target.value)}/></label><label className="os-field"><span>Chat ID</span><input required value={chatId} onChange={e => setChatId(e.target.value)}/></label><button className="os-primary" disabled={telegram.isPending}>{telegram.isPending ? 'Connecting…' : 'Connect Telegram'}</button></form></div>}
  </section>
}

export function ProfileDataPrompt() {
  const { locale } = useI18n()
  const queryClient = useQueryClient()
  const [context, setContext] = useState('profile')
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const [correcting, setCorrecting] = useState(false)
  const completeness = useQuery({ queryKey: ['profile-completeness', context, locale], queryFn: () => api<ProfileCompleteness>(`/profile/completeness?context=${encodeURIComponent(context)}&locale=${locale}`) })
  const current = completeness.data?.missing.find(question => question.generated_by === 'llm')
  const save = useMutation({
    mutationFn: (answer: string) => api<ProfileCompleteness>('/profile/answers', { method: 'POST', body: JSON.stringify({ values: { [current!.memory_key]: answer } }) }),
    onSuccess: async () => {
      setValue('')
      setCorrecting(false)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['profile'] }),
        queryClient.invalidateQueries({ queryKey: ['profile-completeness'] }),
      ])
    },
  })
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ context?: string }>).detail
      setContext(detail?.context || 'profile')
      setOpen(true)
    }
    window.addEventListener('wazzefni:profile-needed', handler)
    return () => window.removeEventListener('wazzefni:profile-needed', handler)
  }, [])
  useEffect(() => { setValue(''); setCorrecting(false) }, [current?.memory_key])
  if (!completeness.data || !completeness.data.cv_reviewed || !current) return null
  const copy = locale === 'ar' ? {
    button: 'راجع بياناتك', eyebrow: 'مراجعة ذكية للسيرة', title: context === 'search' ? 'راجع معلومة قبل البحث' : 'كمّل بياناتك من سيرتك', body: 'حللنا سيرتك، وبنسألك فقط عن معلومة ناقصة أو نتيجة محتاجة تأكيد. مش هنحفظ أي نتيجة قبل موافقتك.', later: 'لاحقًا', save: 'حفظ والتالي', saving: 'جارٍ الحفظ…', progress: 'من البيانات مؤكدة', correct: 'أيوه، صحيح', wrong: 'لأ، أعدّلها', correction: 'اكتب المعلومة الصحيحة', llm: 'السؤال مبني على تحليل السيرة', found: 'المعلومة مكتوبة في السيرة', inferred: 'دي نتيجة استنتجها الذكاء الاصطناعي'
  } : {
    button: 'Review your details', eyebrow: 'AI CV REVIEW', title: context === 'search' ? 'Review one detail before search' : 'Complete your profile from your CV', body: 'We reviewed your CV and only ask about a missing detail or a conclusion that needs confirmation. Nothing is saved without your approval.', later: 'Later', save: 'Save & next', saving: 'Saving…', progress: 'confirmed', correct: 'Yes, that’s right', wrong: 'No, let me fix it', correction: 'Enter the correct information', llm: 'Question based on CV analysis', found: 'This information is written in the CV', inferred: 'This is an AI-derived conclusion'
  }
  return <>
    {!open && <button className="profile-needed-button" onClick={() => setOpen(true)}><UserRound size={16}/><span>{copy.button}</span><i>{completeness.data.percent}%</i></button>}
    {open && <div className="profile-prompt-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setOpen(false) }}><section className="profile-prompt" role="dialog" aria-modal="true" aria-label={copy.title}>
      <button className="profile-prompt-close" onClick={() => setOpen(false)} aria-label={locale === 'ar' ? 'إغلاق' : 'Close'}><X size={18}/></button>
      <div className="profile-prompt-mark"><Sparkles size={19}/></div><p className="os-kicker">{copy.eyebrow}</p><h2>{copy.title}</h2><p>{copy.body}</p>
      <div className="profile-progress"><span><i style={{ width: `${completeness.data.percent}%` }}/></span><b>{completeness.data.percent}% {copy.progress}</b></div>
      <div className={`profile-question-source ${current?.basis || 'missing'}`}><Sparkles size={13}/>{current?.basis === 'explicit' ? copy.found : current?.basis === 'derived' ? copy.inferred : copy.llm}</div>
      {current?.kind === 'confirm' && !correcting ? <div className="profile-confirm"><p>{current.question}</p>{current.reason && <small>{current.reason}</small>}<div><button type="button" className="os-quiet" onClick={() => setOpen(false)}>{copy.later}</button><button type="button" className="os-secondary" onClick={() => setCorrecting(true)}>{copy.wrong}</button><button type="button" className="os-primary" disabled={save.isPending} onClick={() => save.mutate(current.inferred_value)}>{save.isPending ? copy.saving : copy.correct}<Check size={15}/></button></div></div> : <form onSubmit={event => { event.preventDefault(); if (value.trim()) save.mutate(value.trim()) }}><label className="os-field"><span>{correcting ? copy.correction : current?.question}</span>{current?.input_type === 'select' ? <select autoFocus required value={value} onChange={event => setValue(event.target.value)}><option value="">{locale === 'ar' ? 'اختر إجابة' : 'Choose an answer'}</option>{current.options.map(option => <option key={option}>{option}</option>)}</select> : <input autoFocus required type={current?.input_type || 'text'} value={value} onChange={event => setValue(event.target.value)}/>}</label>{current?.reason && !correcting && <small className="profile-question-reason">{current.reason}</small>}<div><button type="button" className="os-quiet" onClick={() => setOpen(false)}>{copy.later}</button><button className="os-primary" disabled={!value.trim() || save.isPending}>{save.isPending ? copy.saving : copy.save}<ArrowRight size={15}/></button></div></form>}
    </section></div>}
  </>
}
