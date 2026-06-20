import { useEffect, useState } from 'react'
import { X, Plus, Pencil, Trash2, RotateCcw, Save, Loader2 } from 'lucide-react'
import type { Agent, Industry } from '../types'
import {
  fetchAgents, fetchAgentDetail, upsertAgent, deleteAgent,
  createIndustry, deleteIndustry, type AgentUpsertBody,
} from '../api/client'

interface Props {
  industries: Industry[]
  currentIndustry: string
  onClose: () => void
  onChanged: () => void   // дёргается после любого изменения (App обновит списки)
}

const ICON_OPTIONS = [
  'sitemap', 'flame', 'building', 'settings', 'bolt',
  'cpu', 'clipboard-check', 'calculator', 'file-description',
]
const COLOR_OPTIONS = [
  '#58A6FF', '#FF7B72', '#79C0FF', '#FFA657', '#F2CC60',
  '#56D364', '#BC8CFF', '#3FB950', '#D2A8FF', '#8B949E',
]

type Form = {
  id: string
  display_name: string
  description: string
  color: string
  icon: string
  system_prompt: string
  keywords: string
  isNew: boolean
  builtin: boolean
}

const EMPTY_FORM: Form = {
  id: '', display_name: '', description: '', color: COLOR_OPTIONS[0],
  icon: 'sitemap', system_prompt: '', keywords: '', isNew: true, builtin: false,
}

export default function AdminModal({ industries, currentIndustry, onClose, onChanged }: Props) {
  const [industry, setIndustry] = useState(
    industries.some((i) => i.id === currentIndustry)
      ? currentIndustry
      : (industries[0]?.id ?? 'ceramics')
  )
  const [agents, setAgents] = useState<Agent[]>([])
  const [form, setForm] = useState<Form | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [newIndustry, setNewIndustry] = useState<{ id: string; name: string } | null>(null)

  const activeInd = industries.find((i) => i.id === industry)

  const reloadAgents = (ind: string) =>
    fetchAgents(ind).then(setAgents).catch((e) => setError(String(e)))

  useEffect(() => { reloadAgents(industry) }, [industry])

  const openNew = () => { setError(''); setForm({ ...EMPTY_FORM }) }

  const openEdit = async (agentId: string) => {
    setError('')
    try {
      const d = await fetchAgentDetail(industry, agentId)
      setForm({
        id: d.id, display_name: d.display_name, description: d.description,
        color: d.color || COLOR_OPTIONS[0], icon: d.icon || 'sitemap',
        system_prompt: d.system_prompt, keywords: d.keywords,
        isNew: false, builtin: d.builtin,
      })
    } catch (e) { setError(String(e)) }
  }

  const saveAgent = async () => {
    if (!form) return
    if (form.isNew && !form.id.trim()) { setError('Укажите id агента'); return }
    if (!form.display_name.trim()) { setError('Укажите название агента'); return }
    setBusy(true); setError('')
    try {
      const body: AgentUpsertBody = {
        display_name: form.display_name, description: form.description,
        color: form.color, icon: form.icon,
        system_prompt: form.system_prompt, keywords: form.keywords,
      }
      await upsertAgent(industry, form.id.trim().toLowerCase(), body)
      setForm(null)
      await reloadAgents(industry)
      onChanged()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }

  const removeAgent = async (a: Agent) => {
    const msg = a.builtin
      ? `Сбросить агента «${a.display_name}» к стандартным настройкам?`
      : `Удалить агента «${a.display_name}»?`
    if (!confirm(msg)) return
    setBusy(true); setError('')
    try {
      await deleteAgent(industry, a.id)
      await reloadAgents(industry)
      onChanged()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }

  const addIndustry = async () => {
    if (!newIndustry) return
    setBusy(true); setError('')
    try {
      await createIndustry(newIndustry.id.trim().toLowerCase(), newIndustry.name.trim())
      setIndustry(newIndustry.id.trim().toLowerCase())
      setNewIndustry(null)
      onChanged()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }

  const removeIndustry = async () => {
    if (!activeInd || activeInd.builtin) return
    if (!confirm(`Удалить отрасль «${activeInd.display_name}» со всеми её агентами?`)) return
    setBusy(true); setError('')
    try {
      await deleteIndustry(industry)
      setIndustry('ceramics')
      onChanged()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-ink-800 border border-ink-600 rounded-xl w-full max-w-3xl max-h-[88vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-600">
          <h2 className="text-sm font-semibold text-gray-100">Управление бюро · агенты и отрасли</h2>
          <button onClick={onClose} className="text-faint hover:text-gray-200"><X size={18} /></button>
        </div>

        {/* Отрасль */}
        <div className="px-5 py-3 border-b border-ink-600 flex items-center gap-2 flex-wrap">
          <span className="text-[11px] text-muted font-mono">Отрасль:</span>
          <select
            value={industry}
            onChange={(e) => { setForm(null); setIndustry(e.target.value) }}
            className="bg-ink-900 border border-ink-500 rounded-lg px-2 py-1 text-[12px] text-gray-200 focus:outline-none focus:border-clay-400"
          >
            {industries.map((i) => (
              <option key={i.id} value={i.id}>
                {i.display_name}{i.builtin ? '' : ' (своя)'}
              </option>
            ))}
          </select>
          {activeInd && !activeInd.builtin && (
            <button onClick={removeIndustry}
              className="text-[11px] text-red-300 hover:text-red-200 flex items-center gap-1">
              <Trash2 size={12} /> удалить отрасль
            </button>
          )}
          <div className="flex-1" />
          {!newIndustry ? (
            <button onClick={() => setNewIndustry({ id: '', name: '' })}
              className="text-[11px] text-clay-300 hover:text-clay-200 flex items-center gap-1">
              <Plus size={13} /> отрасль
            </button>
          ) : (
            <div className="flex items-center gap-1">
              <input placeholder="id (лат.)" value={newIndustry.id}
                onChange={(e) => setNewIndustry({ ...newIndustry, id: e.target.value })}
                className="w-24 bg-ink-900 border border-ink-500 rounded px-2 py-1 text-[12px] text-gray-200" />
              <input placeholder="Название" value={newIndustry.name}
                onChange={(e) => setNewIndustry({ ...newIndustry, name: e.target.value })}
                className="w-40 bg-ink-900 border border-ink-500 rounded px-2 py-1 text-[12px] text-gray-200" />
              <button onClick={addIndustry} disabled={busy || !newIndustry.id.trim()}
                className="px-2 py-1 text-[12px] bg-clay-500 hover:bg-clay-400 disabled:opacity-40 text-white rounded">ОК</button>
              <button onClick={() => setNewIndustry(null)} className="text-faint hover:text-gray-200"><X size={14} /></button>
            </div>
          )}
        </div>

        {error && (
          <div className="mx-5 mt-3 text-xs px-3 py-2 rounded-lg bg-red-950/40 text-red-300 border border-red-900/50 font-mono">
            {error}
          </div>
        )}

        {/* Контент: список агентов или форма */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {!form ? (
            <>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] uppercase tracking-wider text-faint font-mono">Агенты</span>
                <button onClick={openNew}
                  className="text-[12px] text-clay-300 hover:text-clay-200 flex items-center gap-1">
                  <Plus size={14} /> добавить агента
                </button>
              </div>
              <div className="space-y-1.5">
                {agents.map((a) => (
                  <div key={a.id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-ink-900 border border-ink-600">
                    <div className="w-6 h-6 rounded-md shrink-0" style={{ backgroundColor: `${a.color}1A`, border: `1px solid ${a.color}` }} />
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] text-gray-200 truncate">{a.display_name}
                        <span className="text-faint font-mono text-[10px] ml-2">{a.id}</span>
                        {!a.builtin && <span className="text-clay-300 text-[10px] ml-2">своя</span>}
                      </div>
                      <div className="text-[11px] text-faint truncate">{a.description}</div>
                    </div>
                    <button onClick={() => openEdit(a.id)} title="Редактировать"
                      className="p-1.5 rounded hover:bg-ink-600 text-muted hover:text-gray-200"><Pencil size={14} /></button>
                    {a.id !== 'orchestrator' && (
                      <button onClick={() => removeAgent(a)}
                        title={a.builtin ? 'Сбросить к стандартному' : 'Удалить'}
                        className="p-1.5 rounded hover:bg-ink-600 text-muted hover:text-red-300">
                        {a.builtin ? <RotateCcw size={14} /> : <Trash2 size={14} />}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <AgentForm form={form} setForm={setForm} />
          )}
        </div>

        {form && (
          <div className="px-5 py-4 border-t border-ink-600 flex justify-end gap-2">
            <button onClick={() => setForm(null)} className="px-4 py-2 text-sm text-muted hover:text-gray-200">Отмена</button>
            <button onClick={saveAgent} disabled={busy}
              className="px-4 py-2 text-sm bg-clay-500 hover:bg-clay-400 disabled:opacity-40 text-white rounded-lg flex items-center gap-2">
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Сохранить
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function AgentForm({ form, setForm }: { form: Form; setForm: (f: Form) => void }) {
  const upd = (patch: Partial<Form>) => setForm({ ...form, ...patch })
  return (
    <div className="space-y-3">
      <div className="text-[13px] text-gray-200 font-medium">
        {form.isNew ? 'Новый агент' : `Редактирование: ${form.display_name}`}
        {form.builtin && <span className="ml-2 text-[10px] text-faint font-mono">встроенный</span>}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="id (латиница)">
          <input value={form.id} disabled={!form.isNew}
            onChange={(e) => upd({ id: e.target.value })}
            className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 disabled:opacity-50 focus:outline-none focus:border-clay-400" />
        </Field>
        <Field label="Название">
          <input value={form.display_name}
            onChange={(e) => upd({ display_name: e.target.value })}
            className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 focus:outline-none focus:border-clay-400" />
        </Field>
      </div>
      <Field label="Описание">
        <input value={form.description}
          onChange={(e) => upd({ description: e.target.value })}
          className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 focus:outline-none focus:border-clay-400" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Цвет">
          <div className="flex gap-1.5 flex-wrap">
            {COLOR_OPTIONS.map((c) => (
              <button key={c} onClick={() => upd({ color: c })}
                className={`w-6 h-6 rounded-md ${form.color === c ? 'ring-2 ring-white' : ''}`}
                style={{ backgroundColor: c }} />
            ))}
          </div>
        </Field>
        <Field label="Иконка">
          <select value={form.icon} onChange={(e) => upd({ icon: e.target.value })}
            className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 focus:outline-none focus:border-clay-400">
            {ICON_OPTIONS.map((ic) => <option key={ic} value={ic}>{ic}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Системный промпт">
        <textarea value={form.system_prompt} rows={9}
          onChange={(e) => upd({ system_prompt: e.target.value })}
          className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[12px] text-gray-200 font-mono resize-y focus:outline-none focus:border-clay-400" />
      </Field>
      <Field label="Ключевые слова маршрутизации (через запятую)">
        <input value={form.keywords}
          onChange={(e) => upd({ keywords: e.target.value })}
          className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 focus:outline-none focus:border-clay-400" />
      </Field>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] text-muted mb-1 font-mono">{label}</label>
      {children}
    </div>
  )
}
