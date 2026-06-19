import { useEffect, useRef } from 'react'
import { Send, Upload, Trash2, CircleDot } from 'lucide-react'
import type { Agent, ChatMessage } from '../types'

interface Props {
  agents: Agent[]
  selectedAgent: string
  messages: ChatMessage[]
  input: string
  connected: boolean
  busy: boolean
  modelLabel?: string
  onInputChange: (v: string) => void
  onSend: () => void
  onOpenUpload: () => void
  onClear: () => void
}

export default function ChatPanel({
  agents, selectedAgent, messages, input, connected, busy, modelLabel,
  onInputChange, onSend, onOpenUpload, onClear,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)
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
