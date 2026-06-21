import { useEffect, useState } from 'react'
import { X, Loader2, FileText } from 'lucide-react'
import { fetchProjectSpec } from '../api/client'
import type { ProjectSpec } from '../types'

interface Props {
  projectId: string
  projectName: string
  onClose: () => void
  onEditInputs: () => void   // открыть форму исходных данных
}

// Человекочитаемые названия ресурсов расчётного ядра
const RES_LABELS: Record<string, string> = {
  clay_main_t: 'Глина основная, т',
  clay_kaolin_t: 'Глина каолиновая, т',
  sand_t: 'Песок, т',
  water_m3: 'Вода, м³',
  diesel_l: 'Дизтопливо, л',
  oil_l: 'Масло, л',
  electricity_kwh: 'Электроэнергия, кВт·ч',
  gas_m3: 'Газ, м³',
  packaging_pcs: 'Упаковка, шт',
}

const fmt = (n: number) => n.toLocaleString('ru-RU')

export default function SpecModal({ projectId, projectName, onClose, onEditInputs }: Props) {
  const [spec, setSpec] = useState<ProjectSpec | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchProjectSpec(projectId)
      .then(setSpec)
      .catch((e) => setError(e instanceof Error ? e.message : 'Ошибка загрузки'))
  }, [projectId])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-ink-800 border border-ink-600 rounded-xl w-full max-w-2xl max-h-[88vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-600">
          <div className="flex items-center gap-2 min-w-0">
            <FileText size={16} className="text-clay-300 shrink-0" />
            <h2 className="text-sm font-semibold text-gray-100 truncate">
              Спецификация проекта — {projectName}
            </h2>
          </div>
          <button onClick={onClose} className="text-faint hover:text-gray-200"><X size={18} /></button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5 text-[13px]">
          {error && <div className="text-red-300">{error}</div>}
          {!spec && !error && (
            <div className="flex items-center gap-2 text-faint py-8 justify-center">
              <Loader2 size={16} className="animate-spin" /> Расчёт спецификации…
            </div>
          )}

          {spec && !spec.has_data && (
            <div className="text-center py-8">
              <div className="text-muted mb-3">
                Не задан объём выпуска — спецификацию не рассчитать.
              </div>
              <button
                onClick={() => { onClose(); onEditInputs() }}
                className="px-4 py-2 text-sm bg-clay-500 hover:bg-clay-400 text-white rounded-lg"
              >
                Заполнить исходные данные
              </button>
            </div>
          )}

          {spec?.has_data && (
            <>
              {spec.production && (
                <Section title="Производственная программа">
                  <Row k="Выпуск" v={`${fmt(spec.production.pieces_per_year)} шт/год · ${fmt(spec.production.pieces_per_hour)} шт/ч`} />
                  <Row k="Масса продукции" v={`${fmt(spec.production.mass_per_year_t)} т/год`} />
                  <Row k="Масса 1 шт" v={`${spec.production.piece_mass_kg} кг`} />
                </Section>
              )}

              {spec.resources && (
                <Section title="Потребность ресурсов (год)">
                  {Object.entries(spec.resources).map(([k, v]) => (
                    <Row key={k} k={RES_LABELS[k] ?? k} v={fmt(v)} />
                  ))}
                </Section>
              )}

              {spec.equipment && (
                <Section title={`Оборудование (≈${spec.equipment.throughput_tph} т/ч по сырью)`}>
                  {spec.equipment.items.map((it, i) => (
                    <Row key={i} k={`${it.role}: ${it.name}`}
                         v={`${it.unit_capacity} × ${it.qty}`} />
                  ))}
                </Section>
              )}

              {spec.electrical && (
                <Section title="Электроснабжение">
                  <Row k="Установленная мощность" v={`≈ ${fmt(spec.electrical.installed_power_kw)} кВт`} />
                  <Row k="Трансформатор (КТП)" v={`${spec.electrical.transformer_kva} кВА`} />
                  <Row k="Категория" v={spec.electrical.category} />
                </Section>
              )}

              {spec.buildings && spec.buildings.length > 0 && (
                <Section title={`Состав корпусов${spec.areas ? ` (всего ≈ ${fmt(spec.areas.total_m2)} м²)` : ''}`}>
                  {spec.buildings.map((b, i) => (
                    <Row key={i} k={b.name} v={`${b.width_m}×${b.length_m} м`} />
                  ))}
                </Section>
              )}

              {spec.cost && (
                <Section title="Себестоимость (переменные затраты)">
                  <Row k="На 1000 шт" v={`${fmt(spec.cost.cost_per_1000_rub)} ₽`} />
                  <Row k="В год" v={`${fmt(spec.cost.total_per_year_rub)} ₽`} />
                </Section>
              )}
            </>
          )}
        </div>

        <div className="px-5 py-3 border-t border-ink-600 flex items-center justify-between">
          <span className="text-[11px] text-faint">
            Цифры детерминированы расчётным ядром по исходным данным.
          </span>
          <button
            onClick={() => { onClose(); onEditInputs() }}
            className="px-3 py-1.5 text-[13px] text-clay-200 hover:text-clay-100"
          >
            Изменить исходные данные
          </button>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] font-mono uppercase tracking-wide text-clay-300 mb-1.5">{title}</div>
      <div className="bg-ink-900 border border-ink-600 rounded-lg divide-y divide-ink-700">
        {children}
      </div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between gap-4 px-3 py-1.5">
      <span className="text-muted">{k}</span>
      <span className="text-gray-100 text-right font-mono">{v}</span>
    </div>
  )
}
