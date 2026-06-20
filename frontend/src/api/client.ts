import { useEffect, useRef, useState, useCallback } from 'react'
import type { Agent, Industry, Project, ProjectMessageInfo, WsEvent } from '../types'

const API_BASE = '' // proxied via vite

// ─── REST ───────────────────────────────────────────────────────────

export async function fetchIndustries(): Promise<Industry[]> {
  const res = await fetch(`${API_BASE}/api/industries`)
  if (!res.ok) throw new Error('Не удалось загрузить отрасли')
  return res.json()
}

export async function fetchAgents(industry = 'ceramics'): Promise<Agent[]> {
  const res = await fetch(`${API_BASE}/api/agents?industry=${encodeURIComponent(industry)}`)
  if (!res.ok) throw new Error('Не удалось загрузить агентов')
  return res.json()
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/api/projects`)
  if (!res.ok) throw new Error('Не удалось загрузить проекты')
  return res.json()
}

export async function createProject(name: string, industry = 'ceramics'): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, industry }),
  })
  if (!res.ok) throw new Error('Не удалось создать проект')
  return res.json()
}

export async function fetchProjectDetail(
  projectId: string
): Promise<Project & { messages: ProjectMessageInfo[] }> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}`)
  if (!res.ok) throw new Error('Не удалось загрузить проект')
  return res.json()
}

export async function uploadDocument(
  file: File,
  agent: string,
  industry = 'ceramics'
): Promise<{ ok: boolean; chunks_added: number; filename: string }> {
  const form = new FormData()
  form.append('file', file)
  form.append('agent', agent)
  form.append('industry', industry)
  const res = await fetch(`${API_BASE}/api/upload`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка загрузки' }))
    throw new Error(err.detail || 'Ошибка загрузки')
  }
  return res.json()
}

export async function clearSession(sessionId: string): Promise<void> {
  await fetch(`${API_BASE}/api/session/${sessionId}`, { method: 'DELETE' })
}

export type ExportDocType = 'docx' | 'xlsx' | 'pdf'

/** Сформировать документ по проекту и инициировать скачивание файла. */
export async function exportDocument(
  projectId: string,
  docType: ExportDocType
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, doc_type: docType }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка экспорта' }))
    throw new Error(err.detail || 'Ошибка экспорта')
  }
  // Имя файла из заголовка Content-Disposition (filename*=UTF-8'')
  const cd = res.headers.get('Content-Disposition') ?? ''
  const match = /filename\*=UTF-8''([^;]+)/.exec(cd)
  const filename = match ? decodeURIComponent(match[1]) : `document.${docType}`

  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export interface LlmStatus {
  provider: string
  reachable: boolean
  model: string
  model_pulled?: boolean
  hint?: string | null
}

export async function fetchLlmStatus(): Promise<LlmStatus> {
  const res = await fetch(`${API_BASE}/api/llm-status`)
  if (!res.ok) throw new Error('llm-status failed')
  return res.json()
}

// ─── WebSocket hook ─────────────────────────────────────────────────

interface UseChatSocketArgs {
  sessionId: string | null
  onAgentStart: (agent: string, displayName: string) => void
  onToken: (content: string, agent: string) => void
  onDone: (agent: string) => void
  onError: (message: string) => void
}

export function useChatSocket({
  sessionId,
  onAgentStart,
  onToken,
  onDone,
  onError,
}: UseChatSocketArgs) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)

  // Keep latest callbacks without reconnecting
  const cbRef = useRef({ onAgentStart, onToken, onDone, onError })
  cbRef.current = { onAgentStart, onToken, onDone, onError }

  useEffect(() => {
    if (!sessionId) {
      setConnected(false)
      return
    }
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${window.location.host}/ws/${sessionId}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => cbRef.current.onError('Ошибка соединения с сервером')

    ws.onmessage = (e) => {
      const data: WsEvent = JSON.parse(e.data)
      switch (data.type) {
        case 'agent_start':
          cbRef.current.onAgentStart(data.agent, data.display_name)
          break
        case 'token':
          cbRef.current.onToken(data.content, data.agent)
          break
        case 'done':
          cbRef.current.onDone(data.agent)
          break
        case 'error':
          cbRef.current.onError(data.message)
          break
      }
    }

    return () => ws.close()
  }, [sessionId])

  const send = useCallback((message: string, agent: string) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ message, agent, session_id: sessionId }))
    }
  }, [sessionId])

  return { send, connected }
}
