import { useState, useRef } from 'react'
import { Upload, X, FileCheck, Loader2 } from 'lucide-react'
import type { Agent } from '../types'
import { uploadDocument } from '../api/client'

interface Props {
  agents: Agent[]
  defaultAgent: string
  onClose: () => void
}

export default function UploadModal({ agents, defaultAgent, onClose }: Props) {
  const [agent, setAgent] = useState(defaultAgent)
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleUpload = async () => {
    if (!file) return
    setStatus('uploading')
    setMessage('')
    try {
      const res = await uploadDocument(file, agent)
      setStatus('done')
      setMessage(`Добавлено фрагментов: ${res.chunks_added}`)
    } catch (e) {
      setStatus('error')
      setMessage(e instanceof Error ? e.message : 'Ошибка загрузки')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-ink-800 border border-ink-600 rounded-xl w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-600">
          <h2 className="text-sm font-semibold text-gray-100">
            Обучить агента документом
          </h2>
          <button onClick={onClose} className="text-faint hover:text-gray-200">
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-xs text-muted mb-1.5 font-mono">
              База знаний агента
            </label>
            <select
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
              className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-clay-400"
            >
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.display_name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-muted mb-1.5 font-mono">
              Документ (PDF, DOCX, TXT)
            </label>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null)
                setStatus('idle')
              }}
              className="hidden"
            />
            <button
              onClick={() => inputRef.current?.click()}
              className="w-full border border-dashed border-ink-500 rounded-lg px-4 py-6 flex flex-col items-center gap-2 hover:border-clay-400 transition-colors"
            >
              {file ? (
                <>
                  <FileCheck size={22} className="text-clay-300" />
                  <span className="text-sm text-gray-200">{file.name}</span>
                  <span className="text-[11px] text-faint">
                    {(file.size / 1024).toFixed(0)} КБ
                  </span>
                </>
              ) : (
                <>
                  <Upload size={22} className="text-faint" />
                  <span className="text-sm text-muted">Выбрать файл</span>
                </>
              )}
            </button>
          </div>

          {message && (
            <div
              className={`text-xs px-3 py-2 rounded-lg font-mono
                ${status === 'error'
                  ? 'bg-red-950/40 text-red-300 border border-red-900/50'
                  : 'bg-green-950/40 text-green-300 border border-green-900/50'}`}
            >
              {message}
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-ink-600 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-muted hover:text-gray-200"
          >
            Закрыть
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || status === 'uploading'}
            className="px-4 py-2 text-sm bg-clay-500 hover:bg-clay-400 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg flex items-center gap-2 transition-colors"
          >
            {status === 'uploading' && <Loader2 size={14} className="animate-spin" />}
            Загрузить в базу
          </button>
        </div>
      </div>
    </div>
  )
}
