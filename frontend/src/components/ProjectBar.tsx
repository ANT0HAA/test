import { Folder, Plus } from 'lucide-react'
import type { Project } from '../types'

interface Props {
  projects: Project[]
  activeId: string | null
  onSelect: (id: string) => void
  onCreate: (name: string) => void
}

export default function ProjectBar({ projects, activeId, onSelect, onCreate }: Props) {
  const handleCreate = () => {
    const name = window.prompt('Название нового проекта')
    if (name && name.trim()) onCreate(name.trim())
  }

  return (
    <div className="px-6 py-2 border-b border-ink-600 bg-ink-800 flex items-center gap-2">
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
      <button
        onClick={handleCreate}
        className="p-1 rounded-lg hover:bg-ink-600 text-faint hover:text-gray-200 transition-colors"
        title="Новый проект"
      >
        <Plus size={14} />
      </button>
    </div>
  )
}
