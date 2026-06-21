import { useEffect, useRef, useState } from 'react'
import { Send, Upload, Trash2, CircleDot, FileDown, Plus, Loader2, ClipboardList, FileText, History, FolderOpen } from 'lucide-react'
import type { Agent, ChatMessage } from '../types'
import type { ExportDocType } from '../api/client'

interface Props {
  agents: Agent[]
  selectedAgent: string
  messages: ChatMessage[]
  input: string
  connected: boolean
  busy: boolean
  modelLabel?: string
  exporting?: boolean
  onInputChange: (v: string) => void
  onSend: () => void
  onOpenUpload: () => void
  onClear: () => void
  onExport: (docType: ExportDocType) => void
  onDownloadPackage: () => void                  // полный пакет проекта (ZIP)
  onDownloadSitePlan: () => void                 // генплан (Компас, по площадям)
  onOpenSpec: () => void                         // спецификация проекта (расчётное ядро)
  onOpenVersions: () => void                     // история версий артефактов
  onOpenMaterials: () => void                    // данные проекта (распознанные материалы)
  onAddProjectFiles: (files: FileList) => void   // загрузка файлов в проект (кнопка «+»)
  onOpenInputs: (brief: string) => void          // форма исходных данных
  projectUploading?: boolean
}

const EXPORT_OPTIONS: { type: ExportDocType; label: string }[] = [
  { type: 'docx', label: 'Пояснительная записка (DOCX)' },
  { type: 'xlsx', label: 'Ведомость оборудования (XLSX)' },
  { type: 'pdf', label: 'Сводный отчёт (PDF)' },
]

export default function ChatPanel({
  agents, selectedAgent, messages, input, connected, busy, modelLabel, exporting,
  onInputChange, onSend, onOpenUpload, onClear, onExport, onDownloadPackage,
  onDownloadSitePlan, onOpenSpec, onOpenVersions, onOpenMaterials, onAddProjectFiles, onOpenInputs, projectUploading,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const projectFileRef = useRef<HTMLInputElement>(null)
  const [exportOpen, setExportOpen] = useState(false)
  const agentMap = Object.fromEntries(agents.map((a) => [a.id, a]))
  const current = agentMap[selectedAgent]

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <main className="flex-1 flex flex-col h-full bg-ink-900 min-w-0">
      {/* Header */}
      <header className="px-6 py-3.5 border-b border-ink-600 flex items-center justify-between bg-ink-800">
        <div className="flex items-center gap-3 min-w-0">
          {current && (
            <div
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: current.color }}
            />
          )}
          <div className="min-w-0">
            <div className="text-sm font-medium text-gray-100 truncate">
              {current?.display_name ?? 'Агент'}
            </div>
            <div className="text-[11px] text-faint truncate">
              {selectedAgent === 'orchestrator'
                ? 'Распределяет задачи между специалистами'
                : 'Прямой диалог со специалистом'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-[11px] text-faint font-mono mr-1">
            <CircleDot
              size={11}
              className={connected ? 'text-green-400' : 'text-red-400'}
            />
            {modelLabel ?? (connected ? 'онлайн' : 'оффлайн')}
          </span>
          <button
            onClick={onOpenSpec}
            className="p-2 rounded-lg hover:bg-ink-600 text-muted hover:text-gray-200 transition-colors"
            title="Спецификация проекта"
          >
            <FileText size={16} />
          </button>
          <button
            onClick={onOpenMaterials}
            className="p-2 rounded-lg hover:bg-ink-600 text-muted hover:text-gray-200 transition-colors"
            title="Данные проекта (распознанные материалы)"
          >
            <FolderOpen size={16} />
          </button>
          <button
            onClick={onOpenVersions}
            className="p-2 rounded-lg hover:bg-ink-600 text-muted hover:text-gray-200 transition-colors"
            title="История версий"
          >
            <History size={16} />
          </button>
          <div className="relative">
            <button
              onClick={() => setExportOpen((v) => !v)}
              disabled={exporting}
              className="p-2 rounded-lg hover:bg-ink-600 text-muted hover:text-gray-200 transition-colors disabled:opacity-40"
              title="Сформировать документ"
            >
              <FileDown size={16} className={exporting ? 'animate-pulse' : ''} />
            </button>
            {exportOpen && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setExportOpen(false)}
                />
                <div className="absolute right-0 mt-1 z-20 w-64 bg-ink-800 border border-ink-500 rounded-xl shadow-xl py-1">
                  {EXPORT_OPTIONS.map((opt) => (
                    <button
                      key={opt.type}
                      onClick={() => {
                        setExportOpen(false)
                        onExport(opt.type)
                      }}
                      className="w-full text-left px-4 py-2 text-[13px] text-gray-200 hover:bg-ink-600 transition-colors"
                    >
                      {opt.label}
                    </button>
                  ))}
                  <div className="my-1 border-t border-ink-600" />
                  <button
                    onClick={() => {
                      setExportOpen(false)
                      onDownloadSitePlan()
                    }}
                    className="w-full text-left px-4 py-2 text-[13px] text-gray-200 hover:bg-ink-600 transition-colors"
                  >
                    Генплан завода (Компас)
                  </button>
                  <button
                    onClick={() => {
                      setExportOpen(false)
                      onDownloadPackage()
                    }}
                    className="w-full text-left px-4 py-2 text-[13px] text-clay-200 hover:bg-ink-600 transition-colors"
                  >
                    Полный пакет проекта (ZIP)
                  </button>
                </div>
              </>
            )}
          </div>
          <button
            onClick={onOpenUpload}
            className="p-2 rounded-lg hover:bg-ink-600 text-muted hover:text-gray-200 transition-colors"
            title="Обучить документом"
          >
            <Upload size={16} />
          </button>
          <button
            onClick={onClear}
            className="p-2 rounded-lg hover:bg-ink-600 text-muted hover:text-gray-200 transition-colors"
            title="Очистить диалог"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </header>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-3xl mx-auto space-y-5">
          {messages.length === 0 && <EmptyState agent={current} />}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} agent={agentMap[m.agent]} />
          ))}
        </div>
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-ink-600 bg-ink-800">
        <div className="max-w-3xl mx-auto flex gap-2 items-end">
          <input
            ref={projectFileRef}
            type="file"
            multiple
            accept=".pdf,.docx,.xlsx,.xlsm,.txt"
            className="hidden"
            onChange={(e) => {
              if (e.target.files && e.target.files.length) onAddProjectFiles(e.target.files)
              e.target.value = ''
            }}
          />
          <button
            onClick={() => projectFileRef.current?.click()}
            disabled={projectUploading}
            title="Прикрепить файлы к проекту (отчёт лаборатории, готовый проект и т.п.)"
            className="shrink-0 w-11 h-11 rounded-xl border border-ink-500 bg-ink-900 hover:bg-ink-600 text-muted hover:text-gray-200 disabled:opacity-40 flex items-center justify-center transition-colors"
          >
            {projectUploading ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
          </button>
          <button
            onClick={() => onOpenInputs(input)}
            title="Заполнить исходные данные проекта (форма)"
            className="shrink-0 w-11 h-11 rounded-xl border border-ink-500 bg-ink-900 hover:bg-ink-600 text-muted hover:text-gray-200 flex items-center justify-center transition-colors"
          >
            <ClipboardList size={18} />
          </button>
          <textarea
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleKey}
            rows={1}
            placeholder={`Сообщение для «${current?.display_name ?? 'агента'}»...`}
            className="flex-1 resize-none bg-ink-900 border border-ink-500 rounded-xl px-4 py-3 text-sm text-gray-100 placeholder:text-faint focus:outline-none focus:border-clay-400 max-h-40"
          />
          <button
            onClick={onSend}
            disabled={!input.trim() || busy || !connected}
            className="shrink-0 w-11 h-11 rounded-xl bg-clay-500 hover:bg-clay-400 disabled:opacity-30 disabled:cursor-not-allowed text-white flex items-center justify-center transition-colors"
          >
            <Send size={17} />
          </button>
        </div>
      </div>
    </main>
  )
}

function EmptyState({ agent }: { agent?: Agent }) {
  return (
    <div className="text-center py-20">
      <div className="text-sm text-muted mb-1">
        {agent?.display_name ?? 'Агент'} готов к работе
      </div>
      <div className="text-xs text-faint max-w-sm mx-auto leading-relaxed">
        {agent?.id === 'orchestrator'
          ? 'Опишите задачу — Главный конструктор определит, какой специалист её решит, либо ответит сам.'
          : agent?.description}
      </div>
    </div>
  )
}

function MessageBubble({ message, agent }: { message: ChatMessage; agent?: Agent }) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end msg-in">
        <div className="max-w-[80%] bg-clay-600/20 border border-clay-600/30 rounded-2xl rounded-tr-sm px-4 py-2.5">
          <p className="text-sm text-gray-100 whitespace-pre-wrap leading-relaxed">
            {message.content}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3 msg-in">
      <div
        className="shrink-0 w-7 h-7 rounded-md mt-0.5 flex items-center justify-center text-[10px] font-mono font-semibold"
        style={{
          backgroundColor: `${agent?.color ?? '#888'}1A`,
          color: agent?.color ?? '#888',
        }}
      >
        {(agent?.display_name ?? '?').slice(0, 2)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-mono mb-1" style={{ color: agent?.color }}>
          {message.agentName ?? agent?.display_name ?? message.agent}
        </div>
        <div className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">
          {message.content}
          {message.streaming && (
            <span className="cursor-blink ml-0.5 text-clay-300">▊</span>
          )}
        </div>
      </div>
    </div>
  )
}
