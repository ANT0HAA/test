import { useEffect, useState } from 'react'
import { X, Loader2, FileText, FlaskConical } from 'lucide-react'
import { fetchProjectSpec, analyzeLab, fetchProjectLab, fetchLabInputs } from '../api/client'
import type { LabAnalysis, ProjectSpec } from '../types'

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
  const [lab, setLab] = useState<LabAnalysis | null>(null)
  const [labBusy, setLabBusy] = useState(false)
  const [labReport, setLabReport] = useState<any>(null)

  useEffect(() => {
    fetchProjectSpec(projectId)
      .then(setSpec)
      .catch((e) => setError(e instanceof Error ? e.message : 'Ошибка загрузки'))
    // Лаборатория в спецификации — ТОЛЬКО по сохранённым данным проекта (быстро, без LLM).
    // Если глины не сохранены — не дёргаем /lab (там извлечение из отчёта может быть долгим).
    fetchLabInputs(projectId)
      .then((d) => {
        if (d?.clays?.length) {
          fetchProjectLab(projectId)
            .then((r) => { if (r?.has_data) setLabReport(r) })
            .catch(() => { /* пропускаем */ })
        }
      })
      .catch(() => { /* нет сохранённых — секция не показывается */ })
  }, [projectId])

  const runLab = async () => {
    setLabBusy(true)
    try {
      setLab(await analyzeLab(projectId))
    } catch (e) {
      setLab({ found: false, detail: e instanceof Error ? e.message : 'Ошибка разбора' })
    } finally {
      setLabBusy(false)
    }
  }

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

          {spec && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <div className="text-[11px] font-mono uppercase tracking-wide text-clay-300">
                  Химсостав сырья (из отчёта лаборатории)
                </div>
                <button
                  onClick={runLab}
                  disabled={labBusy}
                  className="flex items-center gap-1.5 px-2.5 py-1 text-[11px] rounded-md border border-ink-500 bg-ink-900 hover:bg-ink-600 text-muted hover:text-gray-200 disabled:opacity-40"
                >
                  {labBusy ? <Loader2 size={12} className="animate-spin" /> : <FlaskConical size={12} />}
                  {lab ? 'Разобрать заново' : 'Разобрать отчёт'}
                </button>
              </div>

              {!lab && (
                <div className="text-[11px] text-faint bg-ink-900 border border-ink-600 rounded-lg px-3 py-2">
                  Приложите отчёт лаборатории к проекту (кнопка «+») и нажмите «Разобрать отчёт» —
                  технолог извлечёт компоненты и рассчитает оксидный состав массы.
                </div>
              )}

              {lab && !lab.found && (
                <div className="text-[11px] text-amber-200/80 bg-ink-900 border border-ink-600 rounded-lg px-3 py-2">
                  {lab.detail ?? 'Отчёт лаборатории не найден в материалах проекта.'}
                </div>
              )}

              {lab?.found && (
                <div className="space-y-2">
                  {lab.summary && (
                    <div className="text-[12px] text-gray-300 bg-ink-900 border border-ink-600 rounded-lg px-3 py-2">
                      {lab.summary}
                    </div>
                  )}
                  {lab.components && lab.components.length > 0 && (
                    <div className="bg-ink-900 border border-ink-600 rounded-lg divide-y divide-ink-700">
                      {lab.components.map((c, i) => (
                        <div key={i} className="px-3 py-1.5">
                          <div className="flex items-center justify-between gap-4">
                            <span className="text-muted">{c.name}</span>
                            {c.fraction != null && (
                              <span className="text-gray-100 font-mono">{c.fraction}%</span>
                            )}
                          </div>
                          {c.oxides && Object.keys(c.oxides).length > 0 && (
                            <div className="text-[11px] text-faint font-mono mt-0.5">
                              {Object.entries(c.oxides).map(([k, v]) => `${k} ${v}`).join(' · ')}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {lab.shihta?.composition && Object.keys(lab.shihta.composition).length > 0 && (
                    <div>
                      <div className="text-[11px] text-muted mb-1">Оксидный состав массы (расчёт):</div>
                      <div className="bg-ink-900 border border-ink-600 rounded-lg divide-y divide-ink-700">
                        {Object.entries(lab.shihta.composition).map(([k, v]) => (
                          <Row key={k} k={k} v={`${v} %`} />
                        ))}
                      </div>
                    </div>
                  )}
                  {lab.components && lab.components.length === 0 && (
                    <div className="text-[11px] text-faint">
                      Не удалось извлечь компоненты{lab.error ? `: ${lab.error}` : ''}.
                    </div>
                  )}
                </div>
              )}
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

              {spec.firing && (
                <Section title="Режим обжига (туннельная печь)">
                  <Row k="Макс. температура / время" v={`${spec.firing.max_temp_c} °C · ${spec.firing.residence_h} ч`} />
                  {spec.firing.zones.map((z, i) => (
                    <Row key={i} k={`${z.name} (${z.temp_range_c})`} v={`${z.time_h} ч · ${z.share_pct}%`} />
                  ))}
                  <Row k="Расход газа" v={`${fmt(spec.firing.gas_m3_per_hour)} м³/ч · ${fmt(spec.firing.gas_m3_per_1000)} м³/1000 шт`} />
                </Section>
              )}

              {spec.energy && (
                <Section title="Энергобаланс печь → сушило (рекуперация)">
                  <Row k="Потребность сушила" v={`${fmt(spec.energy.dryer_demand_kcal_per_h)} ккал/ч`} />
                  <Row k="Рекуперация из печи" v={`${fmt(spec.energy.kiln_recoverable_kcal_per_h)} ккал/ч (покрытие ${spec.energy.coverage_pct}%)`} />
                  <Row k="Догрев сушила топливом" v={`${fmt(spec.energy.net_dryer_gas_m3_per_h)} м³/ч газа`} />
                </Section>
              )}

              {spec.grades && (
                <Section title={`Марки и качество (${spec.grades.standard})`}>
                  <Row k="Марка прочности" v={spec.grades.strength} />
                  <Row k="Морозостойкость" v={spec.grades.frost} />
                  <Row k="Водопоглощение" v={spec.grades.water} />
                </Section>
              )}

              {spec.warehouses && (
                <Section title="Склады (запасы)">
                  <Row k={`Сырьё (${spec.warehouses.raw_store_days} сут)`} v={`${fmt(spec.warehouses.raw_store_t)} т`} />
                  <Row k={`Готовая продукция (${spec.warehouses.fg_store_days} сут)`} v={`${fmt(spec.warehouses.fg_pieces)} шт · ${fmt(spec.warehouses.fg_pallets)} поддонов`} />
                  <Row k="Площадь склада ГП" v={`≈ ${fmt(spec.warehouses.fg_area_m2)} м²`} />
                </Section>
              )}

              {spec.staffing && (
                <Section title="Штат (ориентировочно)">
                  <Row k="В смену / смен" v={`${spec.staffing.per_shift} чел · ${spec.staffing.shifts_per_day} см`} />
                  <Row k="Рабочих / ИТР-АУП" v={`${spec.staffing.workers_total} / ${spec.staffing.admin}`} />
                  <Row k="Всего" v={`${spec.staffing.headcount} чел`} />
                </Section>
              )}

              {spec.capex && (
                <Section title="Капзатраты (ориентировочно)">
                  <Row k="Строительство" v={`${fmt(spec.capex.buildings_rub)} ₽`} />
                  {spec.capex.equipment_rub > 0 && <Row k="Оборудование" v={`${fmt(spec.capex.equipment_rub)} ₽`} />}
                  <Row k="Инженерия/монтаж" v={`${fmt(spec.capex.engineering_rub)} ₽`} />
                  <Row k="Итого" v={`${fmt(spec.capex.total_rub)} ₽`} />
                  {spec.capex.payback_years && <Row k="Срок окупаемости" v={`≈ ${spec.capex.payback_years} лет`} />}
                </Section>
              )}

              {spec.ecology && (
                <Section title="Экология">
                  <Row k="Выбросы CO₂ (газ)" v={`≈ ${fmt(spec.ecology.co2_t_per_year)} т/год`} />
                </Section>
              )}

              {spec.balance && (
                <Section title="Материальный баланс по переделам">
                  {spec.balance.stages.map((s, i) => (
                    <Row key={i} k={s.name} v={`${fmt(s.t_per_year)} т/год · ${s.t_per_hour} т/ч`} />
                  ))}
                  <Row k="Вода на затворение" v={`${fmt(spec.balance.forming_water_t_per_year)} т/год`} />
                  <Row k="Удалено влаги (сушка)" v={`${fmt(spec.balance.water_removed_drying_t)} т/год`} />
                  <Row k="Потери при прокаливании (обжиг)" v={`${fmt(spec.balance.loi_removed_firing_t)} т/год`} />
                  <Row k="Брак сушки / обжига" v={`${fmt(spec.balance.reject_drying_t)} / ${fmt(spec.balance.reject_firing_t)} т/год`} />
                </Section>
              )}
            </>
          )}

          {labReport && (
            <Section title={`Лаборатория · сырьё и шихта${labReport.source ? ` (${labReport.source})` : ''}`}>
              <Row k="Усреднённая шихта"
                   v={`Ip ${labReport.blend.plasticity} — ${labReport.blend.group} (глин: ${labReport.blend.clays})`} />
              {labReport.leaning && (
                <Row k="Отощитель (песок)"
                     v={labReport.leaning.need_leaning ? `≈ ${labReport.leaning.sand_fraction_pct}%` : 'не требуется'} />
              )}
              {labReport.feeders && (
                <Row k="Питатели" v={`${labReport.feeders.feeders_used} × ${labReport.feeders.model}`} />
              )}
              {labReport.quarry && (
                <Row k="Выработка карьера" v={`${fmt(labReport.quarry.mined_clay_t)} т/год`} />
              )}
            </Section>
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
