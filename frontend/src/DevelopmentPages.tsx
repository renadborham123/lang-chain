import { FormEvent, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight, BarChart3, BookOpenCheck, Check, CheckCircle2, ChevronRight, CircleAlert, ExternalLink,
  FileCheck2, Flag, Gauge, GraduationCap, LockKeyhole, Mic, Play, RefreshCw, Sparkles, Target,
} from 'lucide-react'
import {
  api, DevelopmentPlan, DevelopmentTask, LearningOpportunity, Readiness, SkillAssessment,
} from './employment-api'
import './development.css'

const isArabic = () => document.documentElement.lang === 'ar'
const copy = (en: string, ar: string) => isArabic() ? ar : en

function TrackLabel({ track }: { track?: string }) {
  const labels: Record<string, [string, string]> = {
    apply_now: ['Apply now', 'قدّم الآن'],
    apply_while_improving: ['Apply while improving', 'قدّم وطور نفسك بالتوازي'],
    development: ['Development track', 'مسار التأهيل'],
  }
  const value = labels[track || 'development'] || labels.development
  return <span className={`readiness-track ${track || 'development'}`}>{copy(value[0], value[1])}</span>
}

export function CareerDevelopmentHub({ onNavigate }: { onNavigate: (page: string) => void }) {
  const readiness = useQuery({ queryKey: ['development-readiness'], queryFn: () => api<Readiness>('/development/readiness') })
  const plan = useQuery({ queryKey: ['development-plan'], queryFn: () => api<DevelopmentPlan>('/development/tasks') })
  const configured = Boolean(readiness.data?.configured)
  const tasks = plan.data?.items || []
  const completed = tasks.filter(task => task.status === 'completed').length
  const activeTask = tasks.find(task => !['completed', 'skipped'].includes(task.status))
  const assessmentReady = Boolean(localStorage.getItem('wazzefni-current-assessment'))
  const primaryTarget = !configured ? 'readiness' : activeTask ? 'development' : 'interviews'
  const primaryLabel = !configured
    ? copy('Diagnose my readiness', 'حلّل جاهزيتي')
    : activeTask
      ? copy('Continue today’s step', 'كمّل خطوة النهارده')
      : copy('Start role-based practice', 'ابدأ تدريب على الوظيفة')

  const modules = [
    {
      id: 'readiness', icon: <Gauge size={19}/>, title: copy('Readiness diagnosis', 'تشخيص الجاهزية'),
      detail: copy('See what is proven, missing, and realistic for your target role.', 'اعرف إيه المثبت وإيه الناقص وإيه الواقعي للوظيفة المستهدفة.'),
      meta: configured ? copy(`${Math.round(readiness.data?.scores?.role_readiness || 0)}% role readiness`, `${Math.round(readiness.data?.scores?.role_readiness || 0)}% جاهزية`) : copy('Start here', 'ابدأ من هنا'),
      target: 'readiness',
    },
    {
      id: 'plan', icon: <Target size={19}/>, title: copy('Qualification plan', 'خطة التأهيل'),
      detail: copy('Work through the smallest useful tasks that close real evidence gaps.', 'اشتغل على أصغر خطوات مفيدة تسد فجوات الدليل الحقيقية.'),
      meta: tasks.length ? copy(`${completed} of ${tasks.length} complete`, `${completed} من ${tasks.length} مكتمل`) : copy('Built after diagnosis', 'بتتبني بعد التشخيص'),
      target: configured ? 'development' : 'readiness',
    },
    {
      id: 'proof', icon: <BookOpenCheck size={19}/>, title: copy('Skill proof', 'إثبات المهارة'),
      detail: copy('Show reasoning and inspectable work before a skill is added to your CV.', 'اثبت فهمك وشغلك قبل إضافة أي مهارة للـCV.'),
      meta: assessmentReady ? copy('Assessment ready', 'التقييم جاهز') : copy('Opened from a plan task', 'بيفتح من مهمة في الخطة'),
      target: assessmentReady ? 'proof' : configured ? 'development' : 'readiness',
    },
    {
      id: 'practice', icon: <Mic size={19}/>, title: copy('Interview practice', 'تدريب المقابلات'),
      detail: copy('Practice for the role using only your confirmed experience and evidence.', 'اتدرّب للوظيفة باستخدام خبرتك وأدلتك المؤكدة فقط.'),
      meta: copy('Part of your development path', 'جزء من مسار تطويرك'), target: 'interviews',
    },
  ]

  return <section className="development-lobby">
    <header className="development-lobby-lead">
      <div>
        <p className="os-kicker">{copy('YOUR DEVELOPMENT PATH', 'مسار تطويرك')}</p>
        <h2>{copy('Build readiness before pressure.', 'جهّز نفسك قبل ضغط التقديم.')}</h2>
        <p>{copy('Diagnosis, focused learning, proof, and interview practice now live in one connected path.', 'التشخيص والتعلّم وإثبات المهارة وتدريب المقابلات بقوا في مسار واحد مترابط.')}</p>
      </div>
      <button onClick={() => onNavigate(primaryTarget)}>{primaryLabel}<ArrowRight size={16}/></button>
    </header>

    <div className="development-lobby-body">
      <section className="development-current">
        <span><Sparkles size={18}/></span>
        <div>
          <small>{copy('RECOMMENDED NEXT', 'الخطوة المقترحة')}</small>
          <h3>{!configured ? copy('Set your target role', 'حدد الوظيفة المستهدفة') : activeTask?.title || copy('Practice the real conversation', 'اتدرّب على المقابلة الحقيقية')}</h3>
          <p>{!configured ? copy('A target lets Wazzefni measure actual gaps instead of giving generic advice.', 'تحديد الوظيفة بيخلّي وظّفني يقيس الفجوات الحقيقية بدل نصايح عامة.') : activeTask?.detail || copy('Your evidence is ready. Rehearse how to explain it clearly for the roles you want.', 'أدلتك جاهزة. اتدرّب تشرحها بوضوح للوظائف اللي مستهدفها.')}</p>
        </div>
        <button onClick={() => onNavigate(primaryTarget)}>{copy('Open', 'افتح')}<ChevronRight size={15}/></button>
      </section>

      <nav className="development-modules" aria-label={copy('Development tools', 'أدوات التطوير')}>
        {modules.map(module => <button key={module.id} onClick={() => onNavigate(module.target)}>
          <span>{module.icon}</span>
          <div><b>{module.title}</b><p>{module.detail}</p><small>{module.meta}</small></div>
          <ChevronRight size={17}/>
        </button>)}
      </nav>
    </div>

    <footer className="development-market-link">
      <BarChart3 size={18}/><div><b>{copy('Need market context?', 'محتاج صورة أوضح للسوق؟')}</b><p>{copy('Research demand, training, and role signals without leaving your development path.', 'ابحث عن الطلب والتدريب وإشارات الوظائف من نفس مسار التطوير.')}</p></div><button onClick={() => onNavigate('growth')}>{copy('Open market research', 'افتح بحث السوق')}<ArrowRight size={15}/></button>
    </footer>
  </section>
}

export function ReadinessPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const client = useQueryClient()
  const readiness = useQuery({ queryKey: ['development-readiness'], queryFn: () => api<Readiness>('/development/readiness') })
  const [role, setRole] = useState('')
  const [level, setLevel] = useState('entry')
  const [location, setLocation] = useState('Cairo, Egypt')
  const diagnose = useMutation({
    mutationFn: () => api<Readiness>('/development/diagnose', { method: 'POST', body: JSON.stringify({ target_role: role, level, location }) }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['development-readiness'] }) },
  })
  const createPlan = useMutation({
    mutationFn: () => api<DevelopmentPlan>('/development/plan', { method: 'POST' }),
    onSuccess: async () => { await client.invalidateQueries({ queryKey: ['development-plan'] }); onNavigate('development') },
  })
  const data = readiness.data
  if (readiness.isLoading) return <div className="qualification-loading"><RefreshCw className="spin" size={17}/>{copy('Calculating your workspace…', 'بنجهّز مساحة التأهيل…')}</div>
  if (!data?.configured) return <section className="readiness-onboarding">
    <p className="os-kicker">{copy('START WITH A DIRECTION', 'ابدأ بهدف واضح')}</p>
    <h2>{copy('What role are you working toward?', 'إيه الوظيفة اللي عايز توصل لها؟')}</h2>
    <p>{copy('Wazzefni will compare your verified evidence with a current market sample. The result is readiness—not a promise of acceptance.', 'وظّفني هيقارن أدلتك الحقيقية بمتطلبات السوق. النتيجة جاهزية، مش وعد بالقبول.')}</p>
    <form onSubmit={(event: FormEvent) => { event.preventDefault(); diagnose.mutate() }}>
      <label><span>{copy('Target role', 'الوظيفة المستهدفة')}</span><input required value={role} onChange={event => setRole(event.target.value)} placeholder={copy('e.g. Junior Data Analyst', 'مثال: محلل بيانات مبتدئ')}/></label>
      <div>
        <label><span>{copy('Starting level', 'مستواك الحالي')}</span><select value={level} onChange={event => setLevel(event.target.value)}><option value="student">Student</option><option value="entry">Entry level</option><option value="career_switcher">Career switcher</option></select></label>
        <label><span>{copy('Market', 'السوق')}</span><input value={location} onChange={event => setLocation(event.target.value)}/></label>
      </div>
      <button disabled={diagnose.isPending}>{diagnose.isPending ? copy('Diagnosing…', 'بنحلل…') : copy('Diagnose my readiness', 'حلّل جاهزيتي')}<ArrowRight size={16}/></button>
      {diagnose.error && <p className="qualification-error">{diagnose.error.message}</p>}
    </form>
  </section>

  const scores = data.scores!
  const scoreRows = [
    ['role_readiness', copy('Role readiness', 'جاهزية الدور'), copy('Coverage of the role requirements we could verify.', 'تغطية متطلبات الدور اللي قدرنا نتحقق منها.')],
    ['evidence_strength', copy('Evidence strength', 'قوة الدليل'), copy('Projects and experience that prove what you can do.', 'المشاريع والخبرة اللي بتثبت إنك تقدر تعمل ده.')],
    ['cv_representation', copy('CV representation', 'تمثيلك في الـCV'), copy('How clearly your CV shows evidence you already have.', 'قد إيه الـCV بيعرض الأدلة الموجودة عندك بوضوح.')],
  ] as const
  return <section className="readiness-page">
    <header className="readiness-lead">
      <div><p className="os-kicker">{copy('YOUR READINESS', 'جاهزيتك')}</p><h2>{data.target_role?.title}</h2><p>{data.explanation}</p></div>
      <div><TrackLabel track={data.track}/><small>{copy(`Snapshot v${data.version}`, `نسخة التقييم ${data.version}`)}</small></div>
    </header>
    <div className="readiness-scores">
      {scoreRows.map(([key, label, description]) => <article key={key}>
        <span>{label}</span><strong>{Math.round(scores[key])}<small>%</small></strong>
        <i><em style={{ width: `${scores[key]}%` }}/></i><p>{description}</p>
      </article>)}
    </div>
    <div className="readiness-breakdown">
      <section>
        <div className="qualification-section-title"><CheckCircle2 size={18}/><div><h3>{copy('Already supported by evidence', 'حاجات عندك عليها دليل')}</h3><p>{data.covered_requirements?.length || 0} {copy('requirements covered', 'متطلبات متغطية')}</p></div></div>
        <div className="requirement-lines">{data.covered_requirements?.length ? data.covered_requirements.map(item => <div key={item.skill_key}><span>{item.label}</span><b>{item.level.replaceAll('_', ' ')}</b></div>) : <p>{copy('No requirement is verified yet. That is a starting point, not a verdict.', 'لسه مفيش متطلب متحقق. دي نقطة بداية، مش حكم عليك.')}</p>}</div>
      </section>
      <section>
        <div className="qualification-section-title"><CircleAlert size={18}/><div><h3>{copy('What to strengthen next', 'إيه اللي محتاج تقويه')}</h3><p>{data.hard_gaps?.length || 0} {copy('hard gaps', 'نواقص أساسية')}</p></div></div>
        <div className="requirement-lines missing">{data.missing_requirements?.map(item => <div key={item.skill_key}><span>{item.label}</span><b>{data.hard_gaps?.some(gap => gap.skill_key === item.skill_key) ? copy('Hard requirement', 'متطلب أساسي') : copy('Needs proof', 'محتاج دليل')}</b></div>)}</div>
      </section>
    </div>
    <footer className="readiness-footer"><p><Gauge size={16}/>{data.score_note}</p><button disabled={createPlan.isPending} onClick={() => createPlan.mutate()}>{createPlan.isPending ? copy('Building your plan…', 'بنبني خطتك…') : copy('Build my qualification plan', 'ابني خطة تأهيلي')}<ArrowRight size={16}/></button></footer>
  </section>
}

function TaskStatus({ status }: { status: string }) {
  const done = status === 'completed'
  return <span className={`task-status ${status}`}>{done ? <Check size={13}/> : status === 'awaiting_assessment' ? <FileCheck2 size={13}/> : <span/>}{status.replaceAll('_', ' ')}</span>
}

export function QualificationPlanPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const client = useQueryClient()
  const plan = useQuery({ queryKey: ['development-plan'], queryFn: () => api<DevelopmentPlan>('/development/tasks') })
  const learning = useQuery({ queryKey: ['learning-opportunities'], queryFn: () => api<{ items: LearningOpportunity[]; score_note: string }>('/development/opportunities') })
  const [expanded, setExpanded] = useState<string | null>(null)
  const [deliverableNote, setDeliverableNote] = useState('')
  const progress = useMutation({
    mutationFn: ({ id, command }: { id: string; command: string }) => api(`/development/tasks/${id}/progress`, { method: 'POST', body: JSON.stringify({ command, deliverable_note: deliverableNote }) }),
    onSuccess: async () => { setDeliverableNote(''); await client.invalidateQueries({ queryKey: ['development-plan'] }) },
  })
  const assessment = useMutation({
    mutationFn: (task: DevelopmentTask) => api<SkillAssessment>(`/development/tasks/${task.id}/assessment`, { method: 'POST', body: JSON.stringify({ assessment_type: task.task_type === 'project' ? 'project_defense' : 'mixed' }) }),
    onSuccess: data => { localStorage.setItem('wazzefni-current-assessment', data.id); onNavigate('proof') },
  })
  if (plan.isLoading) return <div className="qualification-loading"><RefreshCw className="spin" size={17}/>{copy('Loading your next step…', 'بنحمّل خطوتك الجاية…')}</div>
  if (!plan.data?.configured) return <section className="qualification-empty"><Target size={30}/><h2>{copy('Diagnose your readiness first.', 'ابدأ بتشخيص جاهزيتك.')}</h2><p>{copy('Your plan needs a target role and a readiness snapshot.', 'خطة التأهيل محتاجة وظيفة مستهدفة وتقييم جاهزية.')}</p><button onClick={() => onNavigate('readiness')}>{copy('Go to readiness', 'روح للجاهزية')}<ArrowRight size={15}/></button></section>
  const tasks = plan.data.items
  const active = tasks.find(task => !['completed', 'skipped'].includes(task.status))
  return <section className="qualification-plan-page">
    <div className="plan-main">
      <header><div><p className="os-kicker">{copy('QUALIFICATION PLAN', 'خطة تأهيلك')}</p><h2>{copy('One useful step at a time.', 'خطوة مفيدة واحدة كل مرة.')}</h2><p>{plan.data.summary}</p></div><span>v{plan.data.version}</span></header>
      {active && <section className="current-milestone">
        <div className="milestone-index"><Sparkles size={18}/></div>
        <div><small>{copy('YOUR STEP TODAY', 'خطوتك النهارده')}</small><h3>{active.title}</h3><p>{active.detail}</p><div className="impact-line"><span>+{active.readiness_impact}% {copy('possible readiness coverage', 'تغطية جاهزية محتملة')}</span><span>{Math.round((active.market_evidence.frequency || 0) * 100)}% {copy('market frequency', 'تكرار في عينة السوق')}</span></div></div>
        <button onClick={() => { setExpanded(active.id); if (active.status === 'pending') progress.mutate({ id: active.id, command: 'start' }) }}>{copy('Continue', 'كمّل')}<ArrowRight size={15}/></button>
      </section>}
      <div className="task-list-head"><div><h3>{copy('Your to-do list', 'قائمة خطواتك')}</h3><p>{tasks.filter(item => item.status === 'completed').length}/{tasks.length} {copy('completed', 'مكتمل')}</p></div><button onClick={() => client.invalidateQueries({ queryKey: ['development-plan'] })}><RefreshCw size={14}/>{copy('Refresh', 'تحديث')}</button></div>
      <div className="qualification-task-list">{tasks.map((task, index) => <article key={task.id} className={expanded === task.id ? 'expanded' : ''}>
        <button className="task-summary" onClick={() => setExpanded(expanded === task.id ? null : task.id)}>
          <span className="task-number">{String(index + 1).padStart(2, '0')}</span><div><small>{task.task_type.replaceAll('_', ' ')}</small><h4>{task.title}</h4><p>{task.detail}</p></div><TaskStatus status={task.status}/><ChevronRight size={17}/>
        </button>
        {expanded === task.id && <div className="task-detail">
          <div><span>{copy('Deliverable', 'المطلوب تسليمه')}</span><p>{task.deliverable}</p></div>
          <div><span>{copy('How it will be checked', 'طريقة التقييم')}</span><p>{task.assessment_method}</p></div>
          <div><span>{copy('What this can unlock', 'إيه اللي ممكن يفتح بعده')}</span><p>{task.unlocks.join(' · ')}</p></div>
          {!['completed', 'awaiting_assessment'].includes(task.status) && <label><span>{copy('What did you complete?', 'إيه اللي خلصته؟')}</span><textarea value={deliverableNote} onChange={event => setDeliverableNote(event.target.value)} placeholder={copy('Describe the worked example or project. A course completion alone will only count as exposure.', 'اوصف المثال أو المشروع. إنهاء المحتوى لوحده بيتحسب تعرّض للمهارة، مش إثبات كامل.')}/></label>}
          <div className="task-actions">
            {task.status === 'awaiting_assessment' || task.status === 'needs_revision' ? <button className="primary" disabled={assessment.isPending} onClick={() => assessment.mutate(task)}><BookOpenCheck size={15}/>{copy('Prove this skill', 'اثبت المهارة')}</button> : task.status !== 'completed' ? <button className="primary" disabled={!deliverableNote.trim() || progress.isPending} onClick={() => progress.mutate({ id: task.id, command: 'complete' })}><Check size={15}/>{copy('Complete deliverable', 'خلصت المطلوب')}</button> : <span className="completed-note"><CheckCircle2 size={15}/>{copy('Evidence verified', 'الدليل متحقق')}</span>}
            {!['completed', 'skipped'].includes(task.status) && <button onClick={() => progress.mutate({ id: task.id, command: 'snooze' })}>{copy('Snooze', 'أجّل')}</button>}
          </div>
        </div>}
      </article>)}</div>
    </div>
    <aside className="career-ladder">
      <p className="os-kicker">{copy('CAREER LADDER', 'سُلّم الفرص')}</p><h3>{copy('See what each step opens.', 'شوف كل خطوة هتفتح لك إيه.')}</h3>
      <div>{plan.data.milestones.map(item => <article key={item.id} className={item.status}><span>{item.status === 'active' ? <Flag size={14}/> : <LockKeyhole size={13}/>}</span><div><small>{String(item.sequence).padStart(2, '0')}</small><b>{item.title}</b><p>{item.description}</p></div></article>)}</div>
      <section className="training-watchlist"><div><GraduationCap size={17}/><h4>{copy('Named programs to verify', 'برامج بالاسم محتاجة تحقق')}</h4></div>{learning.data?.items.slice(0, 4).map(item => <a key={item.id} href={item.url} target="_blank" rel="noreferrer"><span><b>{item.title}</b><small>{item.provider}</small></span><ExternalLink size={13}/><em>{item.recommendable ? copy('Verified open', 'متاح ومتحقق') : copy('Check official source', 'راجع المصدر الرسمي')}</em></a>)}<p>{learning.data?.score_note}</p></section>
    </aside>
  </section>
}

export function SkillProofPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const client = useQueryClient()
  const assessmentId = localStorage.getItem('wazzefni-current-assessment') || ''
  const assessment = useQuery({ queryKey: ['skill-assessment', assessmentId], enabled: Boolean(assessmentId), queryFn: () => api<SkillAssessment>(`/development/assessments/${assessmentId}`) })
  const [answer, setAnswer] = useState('')
  const [evidenceUrl, setEvidenceUrl] = useState('')
  const [finishResult, setFinishResult] = useState<{ assessment: SkillAssessment; cv_proposal?: { id: string; proposed_text: string; status: string }; remediation_task?: DevelopmentTask } | null>(null)
  const send = useMutation({
    mutationFn: () => api(`/development/assessments/${assessmentId}/turns`, { method: 'POST', body: JSON.stringify({ answer, evidence: evidenceUrl ? { deliverable_url: evidenceUrl } : {} }) }),
    onSuccess: async () => { setAnswer(''); await client.invalidateQueries({ queryKey: ['skill-assessment', assessmentId] }) },
  })
  const finish = useMutation({
    mutationFn: () => api<typeof finishResult>(`/development/assessments/${assessmentId}/finish`, { method: 'POST' }),
    onSuccess: data => { setFinishResult(data); client.invalidateQueries({ queryKey: ['development-plan'] }); client.invalidateQueries({ queryKey: ['development-readiness'] }) },
  })
  const decide = useMutation({ mutationFn: async ({ id, decision }: { id: string; decision: string }) => { const result = await api(`/development/cv-proposals/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision }) }); if (decision === 'approved') await api('/development/recalculate', { method: 'POST' }); return result }, onSuccess: () => { client.invalidateQueries({ queryKey: ['development-readiness'] }); onNavigate('readiness') } })
  const data = assessment.data
  const currentTurn = useMemo(() => data?.turns.find(turn => !turn.answer), [data])
  const answered = data?.turns.filter(turn => turn.answer) || []
  if (!assessmentId) return <section className="qualification-empty"><BookOpenCheck size={30}/><h2>{copy('No skill proof is active.', 'مفيش تقييم مهارة مفتوح.')}</h2><button onClick={() => onNavigate('development')}>{copy('Open your plan', 'افتح خطتك')}</button></section>
  if (assessment.isLoading || !data) return <div className="qualification-loading"><RefreshCw className="spin" size={17}/>{copy('Preparing your assessment…', 'بنجهّز التقييم…')}</div>
  if (finishResult) {
    const passed = finishResult.assessment.outcome === 'pass'
    return <section className={`assessment-result ${passed ? 'pass' : 'retry'}`}><span>{passed ? <CheckCircle2 size={30}/> : <RefreshCw size={30}/>}</span><p className="os-kicker">{passed ? copy('SKILL PROVED', 'المهارة اتثبتت') : copy('ONE MORE PASS', 'محتاج تقوية بسيطة')}</p><h2>{passed ? copy('Your evidence passed the assessment.', 'دليلك عدى التقييم.') : copy('Your readiness score stayed unchanged.', 'درجة جاهزيتك فضلت زي ما هي.')}</h2><p>{passed ? copy('Wazzefni created a CV proposal. Nothing will be published until you approve the exact wording.', 'وظّفني جهّز اقتراح تعديل للـCV. مش هيتغير أي شيء قبل ما توافق على النص.') : copy('A short remediation task was added around the weakest part of your answers.', 'اتضافت لك مهمة تقوية قصيرة حوالين أضعف جزء في إجاباتك.')}</p>{finishResult.cv_proposal && <div className="cv-proposal"><small>{copy('PROPOSED CV TEXT', 'نص الـCV المقترح')}</small><p>{finishResult.cv_proposal.proposed_text}</p><div><button onClick={() => decide.mutate({ id: finishResult.cv_proposal!.id, decision: 'rejected' })}>{copy('Reject', 'ارفض')}</button><button onClick={() => decide.mutate({ id: finishResult.cv_proposal!.id, decision: 'approved' })}>{copy('Approve and recalculate', 'وافق وأعد الحساب')}</button></div></div>} {!finishResult.cv_proposal && <button className="assessment-return" onClick={() => onNavigate('development')}>{copy('Return to my plan', 'ارجع لخطتي')}<ArrowRight size={15}/></button>}</section>
  }
  return <section className="skill-proof-page">
    <header><div><p className="os-kicker">{copy('SKILL PROOF', 'إثبات المهارة')}</p><h2>{data.skill_key.replaceAll('_', ' ')}</h2><p>{copy('Explain what you know, apply it to a scenario, then defend your own work.', 'اشرح اللي فاهمه، طبّقه على موقف، وبعدها دافع عن شغلك بنفسك.')}</p></div><span>{answered.length}/3</span></header>
    <div className="assessment-workspace">
      <aside><Target size={19}/><h3>{copy('How this is scored', 'التقييم بيتحسب إزاي')}</h3>{Object.entries(data.rubric).filter(([key]) => key !== 'pass_score').map(([key, value]) => <p key={key}><span>{key.replaceAll('_', ' ')}</span><b>{value}%</b></p>)}<small>{copy('No personality, emotion, or hiring probability is inferred.', 'مفيش استنتاج للشخصية أو المشاعر أو احتمال القبول.')}</small></aside>
      <main>
        {answered.length > 0 && <div className="assessment-history">{answered.map(turn => <article key={turn.id}><span>{turn.sequence}</span><div><b>{turn.question}</b><p>{turn.answer}</p></div><em>{Math.round(Object.values(turn.evaluation.scores || {}).reduce((sum, value) => sum + value, 0) / Math.max(1, Object.keys(turn.evaluation.scores || {}).length))}%</em></article>)}</div>}
        {currentTurn ? <form onSubmit={(event: FormEvent) => { event.preventDefault(); send.mutate() }}><small>{currentTurn.question_type.replaceAll('_', ' ')} · {copy(`question ${currentTurn.sequence}`, `سؤال ${currentTurn.sequence}`)}</small><h3>{currentTurn.question}</h3><textarea required minLength={12} value={answer} onChange={event => setAnswer(event.target.value)} placeholder={copy('Use your own reasoning and exact contribution…', 'استخدم فهمك ومساهمتك الحقيقية…')}/><label><span>{copy('Deliverable link (optional)', 'رابط المشروع (اختياري)')}</span><input type="url" value={evidenceUrl} onChange={event => setEvidenceUrl(event.target.value)} placeholder="https://github.com/…"/></label><div><span>{answer.trim().split(/\s+/).filter(Boolean).length} {copy('words', 'كلمة')}</span><button disabled={send.isPending || answer.trim().length < 12}>{send.isPending ? copy('Checking…', 'بنراجع…') : copy('Submit answer', 'ابعت الإجابة')}<ArrowRight size={15}/></button></div></form> : <div className="assessment-ready"><CheckCircle2 size={25}/><h3>{copy('Ready to finish.', 'جاهز للنتيجة.')}</h3><p>{copy('Your outcome will be Pass, Partial, or Not yet. A failed proof never invents a CV skill.', 'النتيجة هتكون Pass أو Partial أو Not yet. التقييم مش هيضيف مهارة غير مثبتة للـCV.')}</p><button disabled={finish.isPending} onClick={() => finish.mutate()}>{finish.isPending ? copy('Scoring…', 'بنحسب…') : copy('Finish assessment', 'اظهر النتيجة')}<Flag size={15}/></button></div>}
      </main>
    </div>
  </section>
}
