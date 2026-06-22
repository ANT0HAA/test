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
  balance?: {
    stages: { name: string; t_per_year: number; t_per_hour: number }[]
    raw_dry_t_per_year: number
    forming_water_t_per_year: number
    water_removed_drying_t: number
    loi_removed_firing_t: number
    reject_drying_t: number
    reject_firing_t: number
  }
  firing?: {
    max_temp_c: number
    residence_h: number
    gas_m3_per_hour: number
    gas_m3_per_1000: number
    zones: { name: string; temp_range_c: string; share_pct: number; time_h: number }[]
  }
  energy?: {
    dryer_demand_kcal_per_h: number
    kiln_recoverable_kcal_per_h: number
    coverage_pct: number
    net_dryer_gas_m3_per_h: number
  }
  grades?: { strength: string; frost: string; water: string; control: string[]; standard: string }
  warehouses?: {
    raw_store_days: number; raw_store_t: number
    fg_store_days: number; fg_pieces: number; fg_pallets: number; fg_area_m2: number
  }
  staffing?: { per_shift: number; shifts_per_day: number; workers_total: number; admin: number; headcount: number; by_area: Record<string, number> }
  ecology?: { co2_t_per_year: number; measures: string[] }
  capex?: { buildings_rub: number; equipment_rub: number; engineering_rub: number; total_rub: number; payback_years: number | null }
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

export interface ProjectMaterial {
  id: string
  source: string
  chunk: number
  text: string
}

export interface ProjectVersion {
  id: number
  label: string
  file_name: string
  mime: string
  created_at: string
  has_file: boolean
}

export type WsEvent =
  | { type: 'agent_start'; agent: string; display_name: string }
  | { type: 'token'; content: string; agent: string }
  | { type: 'done'; agent: string }
  | { type: 'error'; message: string }
  | { type: 'clarify'; message: string; agent: string; fields: InputField[] }
