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

export type WsEvent =
  | { type: 'agent_start'; agent: string; display_name: string }
  | { type: 'token'; content: string; agent: string }
  | { type: 'done'; agent: string }
  | { type: 'error'; message: string }
