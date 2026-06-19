import {
  Network, Flame, Building2, Settings, Zap, Cpu,
  ClipboardCheck, Calculator, FileText, type LucideIcon,
} from 'lucide-react'
import type { Agent } from '../types'

const ICONS: Record<string, LucideIcon> = {
  sitemap: Network,
  flame: Flame,
  building: Building2,
  settings: Settings,
  bolt: Zap,
  cpu: Cpu,
  'clipboard-check': ClipboardCheck,
  calculator: Calculator,
  'file-description': FileText,
}

interface Props {
  agents: Agent[]
  selected: string
  onSelect: (id: string) => void
}

export default function Sidebar({ agents, selected, onSelect }: Props) {
  const orchestrator = agents.find((a) => a.id === 'orchestrator')
  const specialists = agents.filter((a) => a.id !== 'orchestrator')

  return (
    <aside className="w-72 shrink-0 bg-ink-800 border-r border-ink-600 flex flex-col h-full">
      <div className="px-5 py-4 border-b border-ink-600">
        <h1 className="text-sm font-semibold text-clay-300 tracking-tight">
          КОНСТРУКТОРСКОЕ БЮРО
        </h1>
        <p className="text-xs text-faint mt-0.5 font-mono">
          керамические заводы · v0.1
        </p>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-3">
        {orchestrator && (
          <AgentButton
            agent={orchestrator}
            active={selected === orchestrator.id}
            onClick={() => onSelect(orchestrator.id)}
            primary
          />
        )}

        <div className="px-2 pt-4 pb-1.5">
          <span className="text-[10px] uppercase tracking-wider text-faint font-mono">
            Специалисты
          </span>
        </div>

        {specialists.map((a) => (
          <AgentButton
            key={a.id}
            agent={a}
            active={selected === a.id}
            onClick={() => onSelect(a.id)}
          />
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-ink-600">
        <p className="text-[10px] text-faint font-mono leading-relaxed">
          Выберите агента для прямого диалога или
          «Главный конструктор» для распределения задач.
        </p>
      </div>
    </aside>
  )
}

function AgentButton({
  agent, active, onClick, primary = false,
}: {
  agent: Agent; active: boolean; onClick: () => void; primary?: boolean
}) {
  const Icon = ICONS[agent.icon] ?? Network

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 rounded-lg mb-1 flex items-start gap-3 transition-colors group
        ${active ? 'bg-ink-600' : 'hover:bg-ink-700'}
        ${primary ? 'border border-ink-500' : ''}`}
    >
      <div
        className="mt-0.5 shrink-0 w-7 h-7 rounded-md flex items-center justify-center"
        style={{ backgroundColor: `${agent.color}1A`, color: agent.color }}
      >
        <Icon size={15} strokeWidth={2} />
      </div>
      <div className="min-w-0 flex-1">
        <div
          className={`text-[13px] font-medium leading-tight truncate
            ${active ? 'text-white' : 'text-gray-200'}`}
        >
          {agent.display_name}
        </div>
        <div className="text-[11px] text-faint leading-snug mt-0.5 line-clamp-2">
          {agent.description}
        </div>
      </div>
    </button>
  )
}
