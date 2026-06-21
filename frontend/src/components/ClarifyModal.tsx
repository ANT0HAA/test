import { useState } from 'react'
import { X, Send, Loader2, HelpCircle } from 'lucide-react'
import type { InputField } from '../types'

interface Props {
  fields: InputField[]
  onClose: () => void                                   // отказаться (не отправлять запрос)
  onSubmit: (values: Record<string, string>) => Promise<void> | void  // сохранить и продолжить
  onProceed: () => void                                 // продолжить без уточнения
}

/**
 * Окно уточняющего вопроса: бюро запросило недостающие исходные данные по ходу
 * проектирования. Пользователь заполняет и продолжает — либо проектирует без них.
 */
export default function ClarifyModal({ fields, onClose, onSubmit, onProceed }: Props) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)

  const set = (k: string, v: string) => setValues((p) => ({ ...p, [k]: v }))

  const submit = async () => {
    setBusy(true)
    try {
      await onSubmit(values)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-ink-800 border border-ink-600 rounded-xl w-full max-w-lg max-h-[88vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-600">
          <div className="flex items-center gap-2">
            <HelpCircle size={16} className="text-clay-300" />
            <h2 className="text-sm font-semibold text-gray-100">Нужны уточнения для проектирования</h2>
          </div>
          <button onClick={onClose} className="text-faint hover:text-gray-200"><X size={18} /></button>
        </div>

        <div className="px-5 py-2 text-[11px] text-faint">
          Чтобы спроектировать корректно, бюро просит указать ключевые данные.
          Остальное система рассчитает сама.
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
          {fields.map((f) => (
            <div key={f.key}>
              <label className="block text-[12px] text-muted mb-1">
                {f.label}{f.unit ? `, ${f.unit}` : ''}
              </label>
              {f.type === 'select' && f.options?.length ? (
                <select
                  value={values[f.key] ?? ''}
                  onChange={(e) => set(f.key, e.target.value)}
                  className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 focus:outline-none focus:border-clay-400"
                >
                  <option value="">— выберите —</option>
                  {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input
                  type={f.type === 'number' ? 'number' : 'text'}
                  value={values[f.key] ?? ''}
                  placeholder={f.placeholder ?? ''}
                  onChange={(e) => set(f.key, e.target.value)}
                  className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder:text-faint focus:outline-none focus:border-clay-400"
                />
              )}
            </div>
          ))}
        </div>

        <div className="px-5 py-4 border-t border-ink-600 flex justify-between gap-2">
          <button onClick={onProceed} className="px-3 py-2 text-[13px] text-muted hover:text-gray-200">
            Проектировать без уточнения
          </button>
          <button onClick={submit} disabled={busy}
            className="px-4 py-2 text-sm bg-clay-500 hover:bg-clay-400 disabled:opacity-40 text-white rounded-lg flex items-center gap-2">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Сохранить и продолжить
          </button>
        </div>
      </div>
    </div>
  )
}
