import { useEffect, useRef, useState, useCallback } from 'react'
import type { Agent, AgentDetail, Industry, InputField, KnowledgeMap, LabAnalysis, Project, ProjectMessageInfo, ProjectSpec, WsEvent } from '../types'

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

export async function fetchKnowledge(industry = 'ceramics'): Promise<KnowledgeMap> {
  const res = await fetch(`${API_BASE}/api/knowledge?industry=${encodeURIComponent(industry)}`)
  if (!res.ok) throw new Error('Не удалось загрузить статистику базы знаний')
  return res.json()
}

export async function fetchAgentDetail(industry: string, agentId: string): Promise<AgentDetail> {
  const res = await fetch(`${API_BASE}/api/agents/${industry}/${agentId}`)
  if (!res.ok) throw new Error('Не удалось загрузить агента')
  return res.json()
}

async function jsonOrThrow(res: Response) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка запроса' }))
    throw new Error(err.detail || 'Ошибка запроса')
  }
  return res.json()
}

export async function createIndustry(id: string, displayName: string) {
  return jsonOrThrow(await fetch(`${API_BASE}/api/industries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, display_name: displayName }),
  }))
}

export async function deleteIndustry(id: string) {
  return jsonOrThrow(await fetch(`${API_BASE}/api/industries/${id}`, { method: 'DELETE' }))
}

export interface AgentUpsertBody {
  display_name?: string
  description?: string
  color?: string
  icon?: string
  system_prompt?: string
  keywords?: string
}

export async function upsertAgent(industry: string, agentId: string, body: AgentUpsertBody) {
  return jsonOrThrow(await fetch(`${API_BASE}/api/agents/${industry}/${agentId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export async function deleteAgent(industry: string, agentId: string) {
  return jsonOrThrow(await fetch(`${API_BASE}/api/agents/${industry}/${agentId}`, { method: 'DELETE' }))
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

export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Не удалось удалить проект')
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

/** Загрузить файл в материалы КОНКРЕТНОГО проекта (приоритет над базой знаний). */
export async function uploadProjectMaterial(
  projectId: string,
  file: File
): Promise<{ ok: boolean; chunks_added: number; filename: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/materials`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка загрузки' }))
    throw new Error(err.detail || 'Ошибка загрузки')
  }
  return res.json()
}

/** Запросить набор полей формы исходных данных (Конструктор предлагает по брифу). */
export async function fetchInputsSchema(projectId: string, brief: string): Promise<InputField[]> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/inputs-schema`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brief }),
  })
  if (!res.ok) throw new Error('Не удалось получить форму данных')
  const data = await res.json()
  return data.fields ?? []
}

/** Сохранить заполненные исходные данные в проект (приоритет над базой знаний). */
export async function submitProjectInputs(
  projectId: string,
  values: Record<string, string>
): Promise<{ ok: boolean; saved: number }> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/inputs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  })
  if (!res.ok) throw new Error('Не удалось сохранить данные')
  return res.json()
}

/** Структурированная спецификация проекта (расчётное ядро по исходным данным). */
export async function fetchProjectSpec(projectId: string): Promise<ProjectSpec> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/spec`)
  if (!res.ok) throw new Error('Не удалось загрузить спецификацию проекта')
  return res.json()
}

/** Разобрать приложенный отчёт лаборатории: компоненты + оксидный состав массы. */
export async function analyzeLab(projectId: string): Promise<LabAnalysis> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/analyze-lab`, { method: 'POST' })
  if (!res.ok) throw new Error('Не удалось разобрать отчёт лаборатории')
  return res.json()
}

/** Сгенерировать и скачать генплан завода по вычисленным площадям (Компас). */
export async function downloadSitePlan(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/site-plan`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка генерации генплана' }))
    throw new Error(err.detail || 'Ошибка генерации генплана')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'Генплан.cdw'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Скачать полный пакет проекта (ZIP с документами и чертежом). */
export async function downloadProjectPackage(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/projects/${projectId}/package`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка формирования пакета' }))
    throw new Error(err.detail || 'Ошибка формирования пакета')
  }
  const cd = res.headers.get('Content-Disposition') ?? ''
  const match = /filename\*=UTF-8''([^;]+)/.exec(cd)
  const filename = match ? decodeURIComponent(match[1]) : 'project_package.zip'
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
