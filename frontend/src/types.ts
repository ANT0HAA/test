export interface Agent {
  id: string
  display_name: string
  description: string
  color: string
  icon: string
  builtin?: boolean
}

export interface Industry {
  id: string
  display_name: string
  builtin?: boolean
}

export interface InputField {
  key: string
  label: string
  type: string          // text | number | select
  unit?: string
  options?: string[]
  placeholder?: string
}

export interface AgentKnowledge {
  chunks: number
  sources: string[]
}

export type KnowledgeMap = Record<string, AgentKnowledge>

export interface AgentDetail {
  id: string
  display_name: string
  description: string
  color: string
  icon: string
  system_prompt: string
  keywords: string
  builtin: boolean
}

export interface Project {
  id: string
  name: string
  industry: string
  created_at: string
}

export interface ProjectMessageInfo {
  role: 'human' | 'ai'
  agent: string
  content: string
  created_at: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  agent: string
  agentName?: string
  content: string
  streaming?: boolean
}

export interface ProjectSpec {
  has_data: boolean
  inputs: Record<string, string>
  production?: {
    pieces_per_year: number
    pieces_per_hour: number
    mass_per_year_t: number
    piece_mass_kg: number
  }
  resources?: Record<string, number>
  equipment?: {
    throughput_tph: number
    items: { role: string; name: string; unit_capacity: number; qty: number }[]
  }
  electrical?: {
    installed_power_kw: number
    transformer_kva: number
    category: string
  }
  areas?: {
    total_m2: number
    items: Record<string, number>
  }
  buildings?: { name: string; width_m: number; length_m: number }[]
  cost?: {
    cost_per_1000_rub: number
    total_per_year_rub: number
  }
}

export interface LabComponent {
  name: string
  fraction?: number
  oxides?: Record<string, number>
}

export interface LabAnalysis {
  found: boolean
  detail?: string
  components?: LabComponent[]
  summary?: string
  error?: string
  shihta?: {
    composition: Record<string, number>
    normalized_fractions: Record<string, number>
    notes?: string[]
  } | null
}

export type WsEvent =
  | { type: 'agent_start'; agent: string; display_name: string }
  | { type: 'token'; content: string; agent: string }
  | { type: 'done'; agent: string }
  | { type: 'error'; message: string }
