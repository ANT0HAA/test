import { useState } from 'react'
import { Folder, Plus, X, Trash2 } from 'lucide-react'
import type { Industry, Project } from '../types'

interface Props {
  projects: Project[]
  activeId: string | null
  industries: Industry[]
  onSelect: (id: string) => void
  onCreate: (name: string, industry: string) => void
  onDelete: (id: string) => void
}

export default function ProjectBar({
  projects, activeId, industries, onSelect, onCreate, onDelete,
}: Props) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [industry, setIndustry] = useState(industries[0]?.id ?? 'ceramics')

  const activeProject = projects.find((p) => p.id === activeId)
  const activeIndustry = industries.find((i) => i.id === activeProject?.industry)

  const submit = () => {
    if (!name.trim()) return
    onCreate(name.trim(), industry)
    setName('')
    setOpen(false)
  }

  return (
    <div className="px-6 py-2 border-b border-ink-600 bg-ink-800 flex items-center gap-2 relative">
      <Folder size={13} className="text-faint shrink-0" />
      <select
        value={activeId ?? ''}
        onChange={(e) => onSelect(e.target.value)}
        className="bg-ink-900 border border-ink-500 rounded-lg px-2 py-1 text-[12px] text-gray-200 focus:outline-none focus:border-clay-400 max-w-[220px]"
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>{p.name}</option>
        ))}
      </select>

      {activeIndustry && (
        <span className="text-[11px] text-faint font-mono px-2 py-0.5 rounded bg-ink-900 border border-ink-600">
          {activeIndustry.display_name}
        </span>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="p-1 rounded-lg hover:bg-ink-600 text-faint hover:text-gray-200 transition-colors"
        title="Новый проект"
      >
        <Plus size={14} />
      </button>
      {activeProject && (
        <button
          onClick={() => {
            if (confirm(`Удалить проект «${activeProject.name}» со всей историей и материалами?`))
              onDelete(activeProject.id)
          }}
          className="p-1 rounded-lg hover:bg-ink-600 text-faint hover:text-red-300 transition-colors"
          title="Удалить проект"
        >
          <Trash2 size={14} />
        </button>
      )}

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute left-6 top-11 z-20 w-80 bg-ink-800 border border-ink-500 rounded-xl shadow-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium text-gray-200">Новый проект</span>
              <button onClick={() => setOpen(false)} className="text-faint hover:text-gray-200">
                <X size={15} />
              </button>
            </div>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
              placeholder="Название проекта"
              className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder:text-faint focus:outline-none focus:border-clay-400"
            />
            <div>
              <label className="block text-[11px] text-muted mb-1 font-mono">Отрасль</label>
              <select
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 focus:outline-none focus:border-clay-400"
              >
                {industries.map((i) => (
                  <option key={i.id} value={i.id}>{i.display_name}</option>
                ))}
              </select>
            </div>
            <button
              onClick={submit}
              disabled={!name.trim()}
              className="w-full px-3 py-2 text-[13px] bg-clay-500 hover:bg-clay-400 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              Создать
            </button>
          </div>
        </>
      )}
    </div>
  )
}
