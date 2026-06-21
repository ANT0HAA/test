import { useEffect, useState } from 'react'
import { X, Loader2, FolderOpen, Trash2, Pencil, Save, ChevronDown, ChevronRight, FileText } from 'lucide-react'
import { fetchMaterials, updateMaterial, deleteMaterial, deleteMaterialSource } from '../api/client'
import type { ProjectMaterial } from '../types'

interface Props {
  projectId: string
  projectName: string
  onClose: () => void
}

export default function MaterialsModal({ projectId, projectName, onClose }: Props) {
  const [items, setItems] = useState<ProjectMaterial[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  const reload = () =>
    fetchMaterials(projectId).then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : 'Ошибка загрузки'))

  useEffect(() => { reload() }, [projectId])

  // Группировка по источнику (файлу)
  const groups: Record<string, ProjectMaterial[]> = {}
  for (const it of items ?? []) (groups[it.source] ||= []).push(it)

  const saveEdit = async (id: string) => {
    setBusy(true)
    try {
      await updateMaterial(projectId, id, draft)
      setEditing(null)
      await reload()
    } catch (e) { setError(e instanceof Error ? e.message : 'Ошибка сохранения') }
    finally { setBusy(false) }
  }

  const removeFrag = async (id: string) => {
    if (!confirm('Удалить этот фрагмент?')) return
    setBusy(true)
    try { await deleteMaterial(projectId, id); await reload() }
    catch (e) { setError(e instanceof Error ? e.message : 'Ошибка удаления') }
    finally { setBusy(false) }
  }

  const removeSource = async (source: string) => {
    if (!confirm(`Удалить все фрагменты файла «${source}» из проекта?`)) return
    setBusy(true)
    try { await deleteMaterialSource(projectId, source); await reload() }
    catch (e) { setError(e instanceof Error ? e.message : 'Ошибка удаления') }
    finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-ink-800 border border-ink-600 rounded-xl w-full max-w-2xl max-h-[88vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-600">
          <div className="flex items-center gap-2 min-w-0">
            <FolderOpen size={16} className="text-clay-300 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-100 truncate">
              Данные проекта — {projectName}
            </h2>
          </div>
          <button onClick={onClose} className="text-faint hover:text-gray-200"><X size={18} /></button>
        </div>

        <div className="px-5 py-2 text-[11px] text-faint">
          Что добавлено в проект из присланных файлов (отчёты, готовые проекты).
          Можно отредактировать или удалить распознанные фрагменты.
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
          {error && <div className="text-red-300 text-[13px]">{error}</div>}
          {!items && !error && (
            <div className="flex items-center gap-2 text-faint py-8 justify-center">
              <Loader2 size={16} className="animate-spin" /> Загрузка…
            </div>
          )}
          {items && items.length === 0 && (
            <div className="text-center text-muted py-8 text-[13px]">
              Пока нет данных. Прикрепите файл кнопкой «+» — распознанный текст появится здесь.
            </div>
          )}

          {Object.entries(groups).map(([source, frags]) => {
            const isOpen = open[source] ?? true
            return (
              <div key={source} className="border border-ink-600 rounded-lg overflow-hidden">
                <div className="flex items-center gap-2 px-3 py-2 bg-ink-900">
                  <button onClick={() => setOpen({ ...open, [source]: !isOpen })}
                    className="text-muted hover:text-gray-200">
                    {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  </button>
                  <FileText size={14} className="text-clay-300 shrink-0" />
                  <span className="text-[13px] text-gray-200 truncate flex-1">{source}</span>
                  <span className="text-[10px] text-faint font-mono">{frags.length} фрагм.</span>
                  <button onClick={() => removeSource(source)} disabled={busy}
                    title="Удалить файл целиком"
                    className="p-1 rounded hover:bg-ink-600 text-muted hover:text-red-300">
                    <Trash2 size={14} />
                  </button>
                </div>
                {isOpen && (
                  <div className="divide-y divide-ink-700">
                    {frags.map((f) => (
                      <div key={f.id} className="px-3 py-2">
                        {editing === f.id ? (
                          <div className="space-y-2">
                            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={6}
                              className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[12px] text-gray-200 resize-y focus:outline-none focus:border-clay-400" />
                            <div className="flex justify-end gap-2">
                              <button onClick={() => setEditing(null)}
                                className="px-3 py-1 text-[12px] text-muted hover:text-gray-200">Отмена</button>
                              <button onClick={() => saveEdit(f.id)} disabled={busy}
                                className="px-3 py-1 text-[12px] bg-clay-500 hover:bg-clay-400 disabled:opacity-40 text-white rounded flex items-center gap-1">
                                {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Сохранить
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-start gap-2">
                            <div className="text-[12px] text-gray-300 whitespace-pre-wrap leading-relaxed flex-1 min-w-0">
                              {f.text.length > 400 ? f.text.slice(0, 400) + '…' : f.text}
                            </div>
                            <div className="flex flex-col gap-1 shrink-0">
                              <button onClick={() => { setEditing(f.id); setDraft(f.text) }}
                                title="Редактировать"
                                className="p-1 rounded hover:bg-ink-600 text-muted hover:text-gray-200"><Pencil size={13} /></button>
                              <button onClick={() => removeFrag(f.id)} disabled={busy}
                                title="Удалить фрагмент"
                                className="p-1 rounded hover:bg-ink-600 text-muted hover:text-red-300"><Trash2 size={13} /></button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
