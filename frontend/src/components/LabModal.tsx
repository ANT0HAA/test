import { useState } from 'react'
import { X, FlaskConical, Plus, Trash2, Loader2, Calculator, FileSearch } from 'lucide-react'
import { calcLab, fetchProjectLab, type LabClay } from '../api/client'

interface Props {
  projectId: string
  projectName: string
  onClose: () => void
}

const FORMING = ['пластическое', 'полусухое', 'сухое']

export default function LabModal({ projectId, projectName, onClose }: Props) {
  const [clays, setClays] = useState<LabClay[]>([])
  const [forming, setForming] = useState('пластическое')
  const [sensitivity, setSensitivity] = useState('')
  const [annualClay, setAnnualClay] = useState('')
  const [rawTph, setRawTph] = useState('')
  const [result, setResult] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [fromReportBusy, setFromReportBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)

  const setClay = (i: number, patch: Partial<LabClay>) =>
    setClays((p) => p.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  const addClay = () => setClays((p) => [...p, { name: `Глина-${p.length + 1}`, plasticity: 15 }])
  const delClay = (i: number) => setClays((p) => p.filter((_, j) => j !== i))

  // Глины и параметры — из отчёта лаборатории (число глин любое; цель считает система)
  const loadFromReport = async () => {
    setFromReportBusy(true); setError(null); setInfo(null)
    try {
      const r = await fetchProjectLab(projectId)
      if (r.annual_clay_t) setAnnualClay(String(Math.round(r.annual_clay_t)))
      if (r.raw_tph) setRawTph(String(r.raw_tph))
      if (r.forming) setForming(r.forming)
      if (r.has_data) {
        if (r.clays_used?.length) setClays(r.clays_used.map((c: any) => ({ name: c.name, plasticity: c.plasticity })))
        setResult(r)
        setInfo('Глины и свойства взяты из отчёта лаборатории. Цель и нагрузки рассчитаны системой.')
      } else {
        setResult(null)
        setInfo(r.reason || 'Не удалось извлечь данные из отчёта — задайте глины вручную.')
      }
    } catch (e) { setError(e instanceof Error ? e.message : 'Ошибка') }
    finally { setFromReportBusy(false) }
  }

  const run = async () => {
    setBusy(true); setError(null)
    try {
      const r = await calcLab({
        clays: clays.filter((c) => c.name.trim()),
        forming, target_plasticity: null,   // null → система считает по способу формования
        sensitivity_coeff: sensitivity ? Number(sensitivity) : null,
        annual_clay_t: annualClay ? Number(annualClay) : 0,
        raw_tph: rawTph ? Number(rawTph) : 0,
        max_feeders: 3,
      })
      setResult(r)
    } catch (e) { setError(e instanceof Error ? e.message : 'Ошибка расчёта') }
    finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-ink-800 border border-ink-600 rounded-xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-600">
          <div className="flex items-center gap-2 min-w-0">
            <FlaskConical size={16} className="text-clay-300 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-100 truncate">Лаборатория — {projectName}</h2>
          </div>
          <button onClick={onClose} className="text-faint hover:text-gray-200"><X size={18} /></button>
        </div>

        <div className="px-5 py-2 text-[11px] text-faint">
          Глины и их свойства берутся ИЗ ОТЧЁТА лаборатории (число глин любое), цель и
          нагрузки рассчитывает система. Можно скорректировать вручную и пересчитать.
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-4">
          <button onClick={loadFromReport} disabled={fromReportBusy}
            className="w-full px-4 py-2 text-sm border border-clay-500/50 bg-clay-600/10 hover:bg-clay-600/20 disabled:opacity-40 text-clay-200 rounded-lg flex items-center justify-center gap-2">
            {fromReportBusy ? <Loader2 size={14} className="animate-spin" /> : <FileSearch size={14} />}
            Взять глины из отчёта лаборатории
          </button>
          {info && <div className="text-[12px] text-amber-200/80 bg-ink-900 border border-ink-600 rounded-lg px-3 py-2">{info}</div>}

          {/* Глины */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] uppercase tracking-wide text-clay-300 font-mono">Глины (компоненты шихты)</span>
              <button onClick={addClay} className="text-[12px] text-clay-300 hover:text-clay-200 flex items-center gap-1">
                <Plus size={13} /> добавить
              </button>
            </div>
            {clays.length === 0 && (
              <div className="text-[12px] text-faint px-3 py-2 bg-ink-900 border border-ink-600 rounded-lg">
                Нет глин. Нажмите «Взять из отчёта лаборатории» или добавьте вручную.
              </div>
            )}
            <div className="space-y-1.5">
              {clays.map((c, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input value={c.name} onChange={(e) => setClay(i, { name: e.target.value })}
                    className="flex-1 bg-ink-900 border border-ink-500 rounded px-2 py-1 text-[12px] text-gray-200" />
                  <label className="text-[11px] text-faint">Ip</label>
                  <input type="number" value={c.plasticity}
                    onChange={(e) => setClay(i, { plasticity: Number(e.target.value) })}
                    className="w-20 bg-ink-900 border border-ink-500 rounded px-2 py-1 text-[12px] text-gray-200" />
                  <button onClick={() => delClay(i)} className="p-1 rounded hover:bg-ink-600 text-muted hover:text-red-300">
                    <Trash2 size={13} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Условия */}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Способ формования">
              <select value={forming} onChange={(e) => setForming(e.target.value)}
                className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200">
                {FORMING.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </Field>
            <Field label="Целевая пластичность Ip">
              <div className="px-3 py-2 text-[13px] text-faint border border-ink-600 rounded-lg bg-ink-900">
                рассчитывается системой по способу формования
              </div>
            </Field>
            <Field label="Коэф. чувствительности к сушке (из отчёта)">
              <input type="number" step="0.1" value={sensitivity} placeholder="напр. 1.8"
                onChange={(e) => setSensitivity(e.target.value)}
                className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200 placeholder:text-faint" />
            </Field>
            <Field label="Годовой расход глины, т (опц.)">
              <input type="number" value={annualClay} onChange={(e) => setAnnualClay(e.target.value)}
                className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2 text-[13px] text-gray-200" />
            </Field>
          </div>

          <button onClick={run} disabled={busy}
            className="px-4 py-2 text-sm bg-clay-500 hover:bg-clay-400 disabled:opacity-40 text-white rounded-lg flex items-center gap-2">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Calculator size={14} />} Рассчитать
          </button>

          {error && <div className="text-red-300 text-[13px]">{error}</div>}

          {result?.has_data && (
            <div className="space-y-3 pt-1">
              <Sec title="Усреднённая шихта">
                <Row k="Пластичность смеси" v={`Ip ${result.blend.plasticity} — ${result.blend.group}`} />
                {Object.entries(result.blend.oxides || {}).length > 0 && (
                  <Row k="Оксидный состав" v={Object.entries(result.blend.oxides).map(([k, v]) => `${k} ${v}`).join(' · ')} />
                )}
              </Sec>

              <Sec title="Отощитель / режим сушки">
                {result.leaning.need_leaning
                  ? <Row k="Песок (отощитель)" v={`≈ ${result.leaning.sand_fraction_pct}%`} />
                  : <Row k="Отощитель" v="не требуется" />}
                {result.leaning.options.map((o: string, i: number) => (
                  <div key={i} className="px-3 py-1.5 text-[12px] text-gray-300">• {o}</div>
                ))}
              </Sec>

              {result.sensitivity && (
                <Sec title="Чувствительность к сушке">
                  <Row k={`Кч = ${result.sensitivity.coeff}`} v={result.sensitivity.group} />
                  <div className="px-3 py-1.5 text-[12px] text-gray-300">{result.sensitivity.recommendation}</div>
                </Sec>
              )}

              <Sec title="Питатели">
                <Row k="Питателей" v={`${result.feeders.feeders_used} × ${result.feeders.model}`} />
                <Row k="Производительность" v={`${result.feeders.unit_capacity_tph} т/ч`} />
              </Sec>

              {result.quarry && (
                <Sec title="Выработка карьера">
                  <Row k="Нужно заводу (полезного)" v={`${result.quarry.usable_clay_t} т/год`} />
                  <Row k="Добыть (с потерями)" v={`${result.quarry.mined_clay_t} т/год`} />
                  <Row k="Объём / вскрыша" v={`${result.quarry.mined_volume_m3} · ${result.quarry.overburden_m3} м³/год`} />
                  {result.quarry.life_years && <Row k="Срок отработки" v={`≈ ${result.quarry.life_years} лет`} />}
                </Sec>
              )}

              {result.yard && (
                <Sec title="Усреднительный штабель">
                  <Row k="Запас" v={`${result.yard.stockpile_t} т`} />
                  <Row k="Слоёв / высота" v={`${result.yard.layers} слоёв · ${result.yard.height_m} м`} />
                  <Row k="Площадь" v={`${result.yard.area_m2} м²`} />
                </Sec>
              )}

              <Sec title={`Формование: ${result.forming.method}`}>
                <Row k="Влажность" v={result.forming.moisture} />
                <Row k="Пресс" v={result.forming.press} />
                <div className="px-3 py-1.5 text-[12px] text-gray-300">Добавки: {result.forming.additive_stage}</div>
              </Sec>

              <Sec title="Контрольные точки для лаборатории">
                {result.control_points.map((c: string, i: number) => (
                  <div key={i} className="px-3 py-1.5 text-[12px] text-gray-300">• {c}</div>
                ))}
              </Sec>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] text-muted mb-1">{label}</label>
      {children}
    </div>
  )
}

function Sec({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] font-mono uppercase tracking-wide text-clay-300 mb-1.5">{title}</div>
      <div className="bg-ink-900 border border-ink-600 rounded-lg divide-y divide-ink-700">{children}</div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-4 px-3 py-1.5">
      <span className="text-muted text-[12px]">{k}</span>
      <span className="text-gray-100 text-[12px] text-right font-mono">{v}</span>
    </div>
  )
}
