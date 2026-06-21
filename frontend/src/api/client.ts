import { useEffect, useRef, useState, useCallback } from 'react'
import type { Agent, AgentDetail, Industry, InputField, KnowledgeMap, LabAnalysis, Project, ProjectMaterial, ProjectMessageInfo, ProjectSpec, ProjectVersion, WsEvent } from '../types'

const API_BASE = '' // proxied via vite

// ─── Авторизация: токен сессии и заголовки ──────────────────────────
let _token: string | null = localStorage.getItem('auth_token')

export function setToken(t: string | null) {
  _token = t
  if (t) localStorage.setItem('auth_token', t)
  else localStorage.removeItem('auth_token')
}
export function getToken(): string | null {
  return _token
}

/** fetch с заголовком Authorization (если есть токен). */
function authedFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {})
  if (_token) headers.set('Authorization', `Bearer ${_token}`)
  return fetch(input, { ...init, headers })
}

export interface AuthUser {
  id: string
  username: string
  role: string
}

export async function authRegister(username: string, password: string): Promise<AuthUser> {
  const res = await authedFetch(`${API_BASE}/api/auth/register`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await jsonOrThrow(res)
  setToken(data.token)
  return data.user
}

export async function authLogin(username: string, password: string): Promise<AuthUser> {
  const res = await authedFetch(`${API_BASE}/api/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await jsonOrThrow(res)
  setToken(data.token)
  return data.user
}

export async function authMe(): Promise<AuthUser | null> {
  if (!_token) return null
  const res = await authedFetch(`${API_BASE}/api/auth/me`)
  if (!res.ok) { setToken(null); return null }
  return res.json()
}

export async function authLogout(): Promise<void> {
  try { await authedFetch(`${API_BASE}/api/auth/logout`, { method: 'POST' }) } catch { /* ignore */ }
  setToken(null)
}

// ─── Управление пользователями (админ) ──────────────────────────────
export async function fetchUsers(): Promise<AuthUser[]> {
  return jsonOrThrow(await authedFetch(`${API_BASE}/api/users`))
}
export async function createUser(username: string, password: string, role: string): Promise<AuthUser> {
  return jsonOrThrow(await authedFetch(`${API_BASE}/api/users`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, role }),
  }))
}
export async function deleteUser(userId: string): Promise<void> {
  await jsonOrThrow(await authedFetch(`${API_BASE}/api/users/${userId}`, { method: 'DELETE' }))
}

// ─── REST ───────────────────────────────────────────────────────────

export async function fetchIndustries(): Promise<Industry[]> {
  const res = await authedFetch(`${API_BASE}/api/industries`)
  if (!res.ok) throw new Error('Не удалось загрузить отрасли')
  return res.json()
}

export async function fetchAgents(industry = 'ceramics'): Promise<Agent[]> {
  const res = await authedFetch(`${API_BASE}/api/agents?industry=${encodeURIComponent(industry)}`)
  if (!res.ok) throw new Error('Не удалось загрузить агентов')
  return res.json()
}

export async function fetchKnowledge(industry = 'ceramics'): Promise<KnowledgeMap> {
  const res = await authedFetch(`${API_BASE}/api/knowledge?industry=${encodeURIComponent(industry)}`)
  if (!res.ok) throw new Error('Не удалось загрузить статистику базы знаний')
  return res.json()
}

export async function fetchAgentDetail(industry: string, agentId: string): Promise<AgentDetail> {
  const res = await authedFetch(`${API_BASE}/api/agents/${industry}/${agentId}`)
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
  return jsonOrThrow(await authedFetch(`${API_BASE}/api/industries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, display_name: displayName }),
  }))
}

export async function deleteIndustry(id: string) {
  return jsonOrThrow(await authedFetch(`${API_BASE}/api/industries/${id}`, { method: 'DELETE' }))
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
  return jsonOrThrow(await authedFetch(`${API_BASE}/api/agents/${industry}/${agentId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export async function deleteAgent(industry: string, agentId: string) {
  return jsonOrThrow(await authedFetch(`${API_BASE}/api/agents/${industry}/${agentId}`, { method: 'DELETE' }))
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await authedFetch(`${API_BASE}/api/projects`)
  if (!res.ok) throw new Error('Не удалось загрузить проекты')
  return res.json()
}

export async function createProject(name: string, industry = 'ceramics'): Promise<Project> {
  const res = await authedFetch(`${API_BASE}/api/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, industry }),
  })
  if (!res.ok) throw new Error('Не удалось создать проект')
  return res.json()
}

export async function deleteProject(projectId: string): Promise<void> {
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Не удалось удалить проект')
}

export async function fetchProjectDetail(
  projectId: string
): Promise<Project & { messages: ProjectMessageInfo[] }> {
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}`)
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
  const res = await authedFetch(`${API_BASE}/api/upload`, {
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
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/materials`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Ошибка загрузки' }))
    throw new Error(err.detail || 'Ошибка загрузки')
  }
  return res.json()
}

export interface LabClay { name: string; plasticity: number; fraction?: number }
export interface LabRequest {
  clays: LabClay[]
  forming: string
  target_plasticity: number | null
  sensitivity_coeff?: number | null
  annual_clay_t?: number
  raw_tph?: number
  max_feeders: number
}

/** Лабораторно-технологический расчёт по сырью (ручной ввод глин). */
export async function calcLab(req: LabRequest): Promise<any> {
  return jsonOrThrow(await authedFetch(`${API_BASE}/api/calc/lab`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }))
}

/** Лабораторный расчёт по проекту: глины и свойства — из отчёта, параметры — авто. */
export async function fetchProjectLab(projectId: string): Promise<any> {
  return jsonOrThrow(await authedFetch(`${API_BASE}/api/projects/${projectId}/lab`, {
    method: 'POST',
  }))
}

/** Список фрагментов материалов проекта (что добавлено) — для просмотра/правки. */
export async function fetchMaterials(projectId: string): Promise<ProjectMaterial[]> {
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/materials`)
  if (!res.ok) throw new Error('Не удалось загрузить материалы проекта')
  return res.json()
}

/** Изменить текст фрагмента материала. */
export async function updateMaterial(projectId: string, fragId: string, text: string): Promise<void> {
  await jsonOrThrow(await authedFetch(
    `${API_BASE}/api/projects/${projectId}/materials/${encodeURIComponent(fragId)}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }))
}

/** Удалить один фрагмент материала. */
export async function deleteMaterial(projectId: string, fragId: string): Promise<void> {
  await jsonOrThrow(await authedFetch(
    `${API_BASE}/api/projects/${projectId}/materials/${encodeURIComponent(fragId)}`,
    { method: 'DELETE' }))
}

/** Удалить все фрагменты одного источника (файла). */
export async function deleteMaterialSource(projectId: string, source: string): Promise<void> {
  await jsonOrThrow(await authedFetch(
    `${API_BASE}/api/projects/${projectId}/materials?source=${encodeURIComponent(source)}`,
    { method: 'DELETE' }))
}

/** Запросить набор полей формы исходных данных (Конструктор предлагает по брифу). */
export async function fetchInputsSchema(projectId: string, brief: string): Promise<InputField[]> {
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/inputs-schema`, {
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
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/inputs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  })
  if (!res.ok) throw new Error('Не удалось сохранить данные')
  return res.json()
}

/** История версий артефактов проекта (снимки при генерации). */
export async function fetchVersions(projectId: string): Promise<ProjectVersion[]> {
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/versions`)
  if (!res.ok) throw new Error('Не удалось загрузить историю версий')
  return res.json()
}

/** Скачать файл сохранённой версии артефакта. */
export async function downloadVersion(projectId: string, versionId: number, fileName: string): Promise<void> {
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/versions/${versionId}`)
  if (!res.ok) throw new Error('Не удалось скачать версию')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName || `version_${versionId}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Структурированная спецификация проекта (расчётное ядро по исходным данным). */
export async function fetchProjectSpec(projectId: string): Promise<ProjectSpec> {
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/spec`)
  if (!res.ok) throw new Error('Не удалось загрузить спецификацию проекта')
  return res.json()
}

/** Разобрать приложенный отчёт лаборатории: компоненты + оксидный состав массы. */
export async function analyzeLab(projectId: string): Promise<LabAnalysis> {
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/analyze-lab`, { method: 'POST' })
  if (!res.ok) throw new Error('Не удалось разобрать отчёт лаборатории')
  return res.json()
}

/** Сгенерировать и скачать генплан завода по вычисленным площадям (Компас). */
export async function downloadSitePlan(projectId: string): Promise<void> {
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/site-plan`, { method: 'POST' })
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
  const res = await authedFetch(`${API_BASE}/api/projects/${projectId}/package`)
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
  await authedFetch(`${API_BASE}/api/session/${sessionId}`, { method: 'DELETE' })
}

export type ExportDocType = 'docx' | 'xlsx' | 'pdf'

/** Сформировать документ по проекту и инициировать скачивание файла. */
export async function exportDocument(
  projectId: string,
  docType: ExportDocType
): Promise<void> {
  const res = await authedFetch(`${API_BASE}/api/export`, {
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
  const res = await authedFetch(`${API_BASE}/api/llm-status`)
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
  onClarify: (message: string, agent: string, fields: InputField[]) => void
}

export function useChatSocket({
  sessionId,
  onAgentStart,
  onToken,
  onDone,
  onError,
  onClarify,
}: UseChatSocketArgs) {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)

  // Keep latest callbacks without reconnecting
  const cbRef = useRef({ onAgentStart, onToken, onDone, onError, onClarify })
  cbRef.current = { onAgentStart, onToken, onDone, onError, onClarify }

  useEffect(() => {
    if (!sessionId) {
      setConnected(false)
      return
    }
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const tokenQs = _token ? `?token=${encodeURIComponent(_token)}` : ''
    const url = `${proto}://${window.location.host}/ws/${sessionId}${tokenQs}`
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
        case 'clarify':
          cbRef.current.onClarify(data.message, data.agent, data.fields)
          break
      }
    }

    return () => ws.close()
  }, [sessionId])

  const send = useCallback((message: string, agent: string, skipClarify = false) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ message, agent, session_id: sessionId, skip_clarify: skipClarify }))
    }
  }, [sessionId])

  return { send, connected }
}
