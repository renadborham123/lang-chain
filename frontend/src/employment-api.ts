export const API = import.meta.env.VITE_API_URL || '/api'

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    credentials: 'include',
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed')
  return data as T
}

export type ApplicationEvent = {
  id: string; from_status: string; to_status: string; source: string; message: string; created_at: string
}
export type TrackedApplication = {
  id: string; opportunity_id?: string; title: string; company: string; location: string; url: string
  status: string; match_score: number; document_id?: string; payload?: Record<string, unknown>; events: ApplicationEvent[]; updated_at: string
}
export type NextAction = {
  id: string; application_id?: string; kind: string; title: string; detail: string; priority: number
  impact: string; confidence: number; due_at?: string; evidence: Record<string, unknown>
}
export type Approval = {
  id: string; action_type: string; target_type: string; target_id: string; summary: string
  payload: Record<string, unknown>; status: string; expires_at?: string
}
export type Interview = {
  id: string; application_id?: string; mode: string; language: 'en' | 'ar'; status: string
  plan: { summary?: string; questions?: string[]; candidate_questions?: string[]; source_note?: string; confidence?: number }
  turns: { id: string; sequence: number; question: string; answer: string; evaluation: InterviewEvaluation }[]
  created_at: string
}
export type InterviewEvaluation = {
  scores: Record<string, number>; strengths: string[]; improvements: string[]; improved_outline: string[]
  delivery?: { word_count?: number; words_per_minute?: number | null; filler_word_count?: number }
  safety_note?: string
}
export type Offer = {
  id: string; application_id?: string; company: string; title: string; currency: string; pay_period: string
  base_salary?: number; bonus?: number; status: string; details: Record<string, unknown>
  components: { id: string; kind: string; label: string; value: string; monetary_value?: number }[]
  created_at: string
}

export type RequirementEvidence = {
  skill_key: string; label: string; level: string; weight: number
  evidence?: Record<string, unknown>
}
export type Readiness = {
  configured: boolean; id?: string; version?: number
  target_role?: { id: string; title: string; domain: string; level: string; location: string; country: string }
  scores?: { role_readiness: number; evidence_strength: number; cv_representation: number }
  track?: 'apply_now' | 'apply_while_improving' | 'development'
  covered_requirements?: RequirementEvidence[]; missing_requirements?: RequirementEvidence[]; hard_gaps?: RequirementEvidence[]
  explanation?: string; score_note?: string; created_at?: string
}
export type DevelopmentTask = {
  id: string; plan_id: string; skill_key: string; task_type: string; title: string; detail: string
  priority: number; status: string; dependencies: string[]; deliverable: string; assessment_method: string
  readiness_impact: number; market_evidence: { sample_size?: number; frequency?: number; importance?: number; hard_requirement?: boolean; examples?: unknown[] }
  unlocks: string[]; due_at?: string; completed_at?: string; created_at: string
}
export type DevelopmentPlan = {
  configured: boolean; id?: string; version?: number; status?: string; summary?: string
  rationale?: Record<string, unknown>; items: DevelopmentTask[]
  milestones: { id: string; sequence: number; kind: string; title: string; description: string; status: string }[]
  updated_at?: string
}
export type LearningOpportunity = {
  id: string; provider: string; title: string; url: string; source_type: string; opportunity_type: string
  status: string; requirements: string[]; skill_tags: string[]; cost: string; location: string; deadline?: string
  relevance: number; eligibility_readiness: number; verified_at?: string; expired: boolean; recommendable: boolean; verification_note: string
}
export type SkillAssessment = {
  id: string; task_id: string; skill_key: string; assessment_type: string; status: string; outcome: string
  rubric: Record<string, number>; scores: Record<string, number>; confidence: number
  turns: { id: string; sequence: number; question_type: string; question: string; answer: string; evaluation: { scores?: Record<string, number>; improvements?: string[] } }[]
}
