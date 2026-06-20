import { useState, useEffect, useCallback, useRef } from 'react'
import Sidebar from './components/Sidebar'
import ChatPanel from './components/ChatPanel'
import UploadModal from './components/UploadModal'
import ProjectBar from './components/ProjectBar'
import AdminModal from './components/AdminModal'
import {
  fetchAgents, useChatSocket, clearSession, fetchLlmStatus, type LlmStatus,
  fetchProjects, createProject, fetchProjectDetail, fetchIndustries, fetchKnowledge,
  exportDocument, type ExportDocType,
} from './api/client'
import type { Agent, ChatMessage, Industry, KnowledgeMap, Project } from './types'

const DEFAULT_INDUSTRY = 'ceramics'

export default function App() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgent, setSelectedAgent] = useState('orchestrator')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  const [llm, setLlm] = useState<LlmStatus | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null)
  const [industries, setIndustries] = useState<Industry[]>([])
  const [exporting, setExporting] = useState(false)
  const [showAdmin, setShowAdmin] = useState(false)
  const [knowledge, setKnowledge] = useState<KnowledgeMap>({})

  // Ref to the id of the currently-streaming assistant message
  const streamingId = useRef<string | null>(null)

  // Текущая отрасль определяется активным проектом (у каждого проекта своя отрасль)
  const activeProject = projects.find((p) => p.id === activeProjectId)
  const currentIndustry = activeProject?.industry ?? DEFAULT_INDUSTRY

  useEffect(() => {
    fetchLlmStatus().then(setLlm).catch(() => setLlm(null))
    fetchIndustries().then(setIndustries).catch(console.error)

    fetchProjects()
      .then(async (list) => {
        if (list.length === 0) {
          const created = await createProject('Проект по умолчанию')
          setProjects([created])
          setActiveProjectId(created.id)
        } else {
          setProjects(list)
          setActiveProjectId(list[0].id)
        }
      })
      .catch(console.error)
  }, [])

  // Набор агентов и статистика базы знаний зависят от отрасли активного проекта
  useEffect(() => {
    fetchAgents(currentIndustry)
      .then((list) => {
        setAgents(list)
        // Если выбранного агента нет в новой отрасли — вернуться к оркестратору
        setSelectedAgent((cur) =>
          list.some((a) => a.id === cur) ? cur : 'orchestrator'
        )
      })
      .catch(console.error)
    fetchKnowledge(currentIndustry).then(setKnowledge).catch(console.error)
  }, [currentIndustry])

  const refreshKnowledge = () =>
    fetchKnowledge(currentIndustry).then(setKnowledge).catch(console.error)

  // При переключении проекта — подгружаем его историю чата
  useEffect(() => {
    if (!activeProjectId) return
    fetchProjectDetail(activeProjectId)
      .then((detail) => {
        setMessages(
          detail.messages.map((m) => ({
            id: crypto.randomUUID(),
            role: m.role === 'human' ? 'user' : 'assistant',
            agent: m.agent,
            content: m.content,
          }))
        )
      })
      .catch(console.error)
  }, [activeProjectId])

  const handleCreateProject = async (name: string, industry: string) => {
    const created = await createProject(name, industry)
    setProjects((prev) => [created, ...prev])
    setActiveProjectId(created.id)
  }

  const llmReady =
    llm?.reachable && (llm.provider !== 'ollama' || llm.model_pulled !== false)

  // ─── WebSocket callbacks ─────────────────────────────────────────

  const handleAgentStart = useCallback((agent: string, displayName: string) => {
    // New assistant message begins (covers delegation and multi-agent plans:
    // each agent gets its own bubble). Finalize the previous streaming bubble
    // so the blinking cursor only shows on the currently active agent.
    const prevId = streamingId.current
    const id = crypto.randomUUID()
    streamingId.current = id
    setMessages((prev) => [
      ...prev.map((m) =>
        m.id === prevId ? { ...m, streaming: false } : m
      ),
      {
        id,
        role: 'assistant',
        agent,
        agentName: displayName,
        content: '',
        streaming: true,
      },
    ])
  }, [])

  const handleToken = useCallback((content: string, agent: string) => {
    const id = streamingId.current
    if (!id) return
    setMessages((prev) =>
      prev.map((m) =>
        m.id === id ? { ...m, content: m.content + content, agent } : m
      )
    )
  }, [])

  const handleDone = useCallback(() => {
    const id = streamingId.current
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, streaming: false } : m))
    )
    streamingId.current = null
    setBusy(false)
  }, [])

  const handleError = useCallback((message: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'assistant',
        agent: 'orchestrator',
        agentName: 'Система',
        content: `⚠ ${message}`,
        streaming: false,
      },
    ])
    streamingId.current = null
    setBusy(false)
  }, [])

  const { send, connected } = useChatSocket({
    sessionId: activeProjectId,
    onAgentStart: handleAgentStart,
    onToken: handleToken,
    onDone: handleDone,
    onError: handleError,
  })

  // ─── Actions ─────────────────────────────────────────────────────

  const handleSend = () => {
    const text = input.trim()
    if (!text || busy || !connected) return

    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: 'user',
        agent: 'user',
        content: text,
      },
    ])
    send(text, selectedAgent)
    setInput('')
    setBusy(true)
  }

  const handleClear = async () => {
    if (!activeProjectId) return
    await clearSession(activeProjectId)
    setMessages([])
  }

  // После изменений в панели управления — обновить отрасли и агентов текущей отрасли
  const handleAdminChanged = () => {
    fetchIndustries().then(setIndustries).catch(console.error)
    fetchAgents(currentIndustry)
      .then((list) => {
        setAgents(list)
        setSelectedAgent((cur) => (list.some((a) => a.id === cur) ? cur : 'orchestrator'))
      })
      .catch(console.error)
  }

  const handleExport = async (docType: ExportDocType) => {
    if (!activeProjectId || exporting) return
    setExporting(true)
    try {
      await exportDocument(activeProjectId, docType)
    } catch (e) {
      handleError(e instanceof Error ? e.message : 'Ошибка экспорта')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex h-full">
      <Sidebar
        agents={agents}
        selected={selectedAgent}
        onSelect={setSelectedAgent}
        onOpenAdmin={() => setShowAdmin(true)}
        knowledge={knowledge}
        industryName={activeProject?.industry === 'ceramics' || !activeProject
          ? 'керамические заводы'
          : industries.find((i) => i.id === currentIndustry)?.display_name ?? currentIndustry}
      />
      <div className="flex-1 flex flex-col min-w-0">
        <ProjectBar
          projects={projects}
          activeId={activeProjectId}
          industries={industries}
          onSelect={setActiveProjectId}
          onCreate={handleCreateProject}
        />
        {llm && !llmReady && (
          <div className="bg-amber-950/40 border-b border-amber-900/50 px-6 py-2.5 text-[12px] text-amber-200 font-mono flex items-center gap-2">
            <span className="text-amber-400">●</span>
            {llm.hint ?? `Модель ${llm.model} не готова`}
          </div>
        )}
        <ChatPanel
          agents={agents}
          selectedAgent={selectedAgent}
          messages={messages}
          input={input}
          connected={connected}
          busy={busy}
          modelLabel={llm?.model}
          exporting={exporting}
          onInputChange={setInput}
          onSend={handleSend}
          onOpenUpload={() => setShowUpload(true)}
          onClear={handleClear}
          onExport={handleExport}
        />
      </div>
      {showUpload && (
        <UploadModal
          agents={agents}
          defaultAgent={selectedAgent}
          industry={currentIndustry}
          knowledge={knowledge}
          onUploaded={refreshKnowledge}
          onClose={() => setShowUpload(false)}
        />
      )}
      {showAdmin && (
        <AdminModal
          industries={industries}
          currentIndustry={currentIndustry}
          onClose={() => setShowAdmin(false)}
          onChanged={handleAdminChanged}
        />
      )}
    </div>
  )
}
