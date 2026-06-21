import { useEffect, useState } from 'react'
import { X, Loader2, History, Download } from 'lucide-react'
import { fetchVersions, downloadVersion } from '../api/client'
import type { ProjectVersion } from '../types'

interface Props {
  projectId: string
  projectName: string
  onClose: () => void
}

export default function VersionsModal({ projectId, projectName, onClose }: Props) {
  const [versions, setVersions] = useState<ProjectVersion[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchVersions(projectId)
      .then(setVersions)
      .catch((e) => setError(e instanceof Error ? e.message : 'Ошибка загрузки'))
  }, [projectId])

  const fmtDate = (iso: string) => {
    const d = new Date(iso)
    return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-ink-800 border border-ink-600 rounded-xl w-full max-w-xl max-h-[88vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-600">
          <div className="flex items-center gap-2 min-w-0">
            <History size={16} className="text-clay-300 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-100 truncate">
              История версий — {projectName}
            </h2>
          </div>
          <button onClick={onClose} className="text-faint hover:text-gray-200"><X size={18} /></button>
        </div>

        <div className="px-5 py-2 text-[11px] text-faint">
          Версии сохраняются автоматически при каждой генерации документа, пакета или генплана.
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3">
          {error && <div className="text-red-300 text-[13px]">{error}</div>}
          {!versions && !error && (
            <div className="flex items-center gap-2 text-faint py-8 justify-center">
              <Loader2 size={16} className="animate-spin" /> Загрузка истории…
            </div>
          )}
          {versions && versions.length === 0 && (
            <div className="text-center text-muted py-8 text-[13px]">
              Пока нет сохранённых версий. Сформируйте документ, пакет или генплан —
              версия сохранится автоматически.
            </div>
          )}
          {versions && versions.length > 0 && (
            <div className="space-y-1.5">
              {versions.map((v) => (
                <div key={v.id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-ink-900 border border-ink-600">
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] text-gray-200 truncate">{v.label}</div>
                    <div className="text-[11px] text-faint font-mono">
                      {fmtDate(v.created_at)}{v.file_name ? ` · ${v.file_name}` : ''}
                    </div>
                  </div>
                  {v.has_file && (
                    <button
                      onClick={() => downloadVersion(projectId, v.id, v.file_name)}
                      title="Скачать версию"
                      className="shrink-0 p-1.5 rounded hover:bg-ink-600 text-muted hover:text-gray-200"
                    >
                      <Download size={15} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
