<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { formatBoutDate, formatShortDate, plural, signed } from '../format'
import type { RatingHistoryPoint } from '../types'

/**
 * График очков или номера в таблице по боям игрока. По оси X — бои по порядку,
 * первая точка — значение до первого показанного боя. Наведение или касание показывает бой.
 *
 * Масштаб: кнопки «+ / − / Весь график», на компьютере ещё Ctrl + колесо (и щипок на тачпаде),
 * на телефоне — двумя пальцами. Приближенный график сдвигается перетаскиванием по горизонтали.
 */
const props = defineProps<{ history: RatingHistoryPoint[]; mode: 'points' | 'place' }>()

const HEIGHT = 220
const PAD = { top: 14, right: 14, bottom: 26, left: 46 }
// Чемпион стоит над №1: на шкале мест у него своя строка над единицей.
const CHAMPION_ROW = 0
// Точки рисуются, пока они не сливаются; при большем числе боёв видна только выбранная.
const MAX_MARKERS = 50
// Сильнее всего можно приблизить до стольких боёв на экране.
const MIN_SPAN = 4
const ZOOM_STEP = 2
// Сдвиг пальцем меньше этого считается касанием, а не перетаскиванием.
const DRAG_THRESHOLD = 6

const box = ref<HTMLElement | null>(null)
const width = ref(600)
const active = ref<number | null>(null)
let observer: ResizeObserver | null = null

/** На телефоне нет «ухода» указателя с графика: подсказку закрывает касание в любом другом месте. */
function closeOnOutsideTap(event: PointerEvent): void {
  const svg = box.value?.querySelector('svg')
  if (svg && event.target instanceof Node && svg.contains(event.target)) return
  active.value = null
}

onMounted(() => {
  document.addEventListener('pointerdown', closeOnOutsideTap)
  if (!box.value) return
  width.value = box.value.clientWidth
  observer = new ResizeObserver(([entry]) => {
    width.value = entry.contentRect.width
  })
  observer.observe(box.value)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', closeOnOutsideTap)
  observer?.disconnect()
})

interface Point {
  value: number
  item: RatingHistoryPoint | null
  /** Держал ли игрок основной пояс после этой точки (до следующего боя). */
  champion: boolean
}

function placeValue(place: number | null, champion: boolean): number {
  return champion ? CHAMPION_ROW : (place ?? CHAMPION_ROW)
}

/** Первая точка — состояние до первого боя, дальше — после каждого боя. */
const points = computed<Point[]>(() => {
  const items = props.history
  if (!items.length) return []
  const first = items[0]
  const start =
    props.mode === 'points'
      ? first.points_before
      : placeValue(first.table_place_before, first.champion_before)
  return [
    { value: start, item: null, champion: first.champion_before },
    ...items.map((item) => ({
      value: props.mode === 'points' ? item.points_after : placeValue(item.table_place_after, item.champion_after),
      item,
      champion: item.champion_after,
    })),
  ]
})

// Видимое окно по оси X в номерах точек: [viewStart, viewEnd].
const lastIndex = computed(() => Math.max(points.value.length - 1, 0))
const viewStart = ref(0)
const viewEnd = ref(0)
const span = computed(() => Math.max(viewEnd.value - viewStart.value, 1e-6))
const minSpan = computed(() => Math.min(MIN_SPAN, lastIndex.value))
const zoomed = computed(() => lastIndex.value > 0 && span.value < lastIndex.value - 0.01)

function resetView(): void {
  viewStart.value = 0
  viewEnd.value = lastIndex.value
  active.value = null
}
watch(() => [props.history, props.mode], resetView, { immediate: true })

/** Новое окно шириной nextSpan так, чтобы точка center осталась на том же месте экрана. */
function zoomAround(nextSpan: number, center: number): void {
  const full = lastIndex.value
  if (full <= 0) return
  const clamped = Math.min(Math.max(nextSpan, minSpan.value), full)
  const share = (center - viewStart.value) / span.value
  let start = center - share * clamped
  start = Math.min(Math.max(start, 0), full - clamped)
  viewStart.value = start
  viewEnd.value = start + clamped
}

function panBy(delta: number): void {
  const full = lastIndex.value
  const start = Math.min(Math.max(viewStart.value + delta, 0), full - span.value)
  viewEnd.value = start + span.value
  viewStart.value = start
}

function zoomIn(): void {
  zoomAround(span.value / ZOOM_STEP, (viewStart.value + viewEnd.value) / 2)
}

function zoomOut(): void {
  zoomAround(span.value * ZOOM_STEP, (viewStart.value + viewEnd.value) / 2)
}

const plotWidth = computed(() => Math.max(width.value - PAD.left - PAD.right, 10))
const plotHeight = HEIGHT - PAD.top - PAD.bottom

/** Точки, попавшие в окно, плюс по одной соседней с каждой стороны, чтобы линия не обрывалась. */
const visibleRange = computed(() => ({
  from: Math.max(0, Math.floor(viewStart.value) - 1),
  to: Math.min(lastIndex.value, Math.ceil(viewEnd.value) + 1),
}))

function inView(index: number): boolean {
  return index >= viewStart.value - 1e-6 && index <= viewEnd.value + 1e-6
}

/** Шкала Y по видимым точкам: для очков — с запасом и «круглыми» делениями, для мест — целые номера, №1 сверху. */
const scale = computed(() => {
  const values = points.value.filter((_, index) => inView(index)).map((point) => point.value)
  if (!values.length) values.push(...points.value.map((point) => point.value))
  let low = Math.min(...values)
  let high = Math.max(...values)
  if (props.mode === 'place') {
    high = Math.max(high, low + 1)
    const step = Math.max(1, Math.ceil((high - low) / 5))
    // Всегда подписаны края шкалы и №1, если он в диапазоне; остальные — с шагом.
    const wanted = new Set([low, high])
    if (low <= 1 && high >= 1) wanted.add(1)
    for (let value = Math.ceil(low / step) * step; value <= high; value += step) wanted.add(value)
    const ticks = [...wanted].sort((a, b) => a - b)
    return { low, high, ticks }
  }
  const range = Math.max(high - low, 20)
  const step = [5, 10, 20, 25, 50, 100, 200].find((candidate) => range / candidate <= 5) ?? 500
  low = Math.floor((low - range * 0.08) / step) * step
  high = Math.ceil((high + range * 0.08) / step) * step
  const ticks: number[] = []
  for (let value = low; value <= high; value += step) ticks.push(value)
  return { low, high, ticks }
})

function x(index: number): number {
  if (lastIndex.value === 0) return PAD.left + plotWidth.value / 2
  return PAD.left + ((index - viewStart.value) / span.value) * plotWidth.value
}

function y(value: number): number {
  const { low, high } = scale.value
  const share = high === low ? 0.5 : (value - low) / (high - low)
  // Для очков больше — выше; для мест меньший номер — выше.
  return props.mode === 'points' ? PAD.top + (1 - share) * plotHeight : PAD.top + share * plotHeight
}

const path = computed(() => {
  const list = points.value
  const { from, to } = visibleRange.value
  if (!list.length) return ''
  let line = `M${x(from)},${y(list[from].value)}`
  for (let index = from + 1; index <= to; index += 1) {
    // Место меняется ступенькой: номер держится до следующего боя.
    line += props.mode === 'place' ? `H${x(index)}V${y(list[index].value)}` : `L${x(index)},${y(list[index].value)}`
  }
  return line
})

/** Деления без наложения подписей: соседние ближе 12px пропускаются. */
const visibleTicks = computed(() => {
  const result: number[] = []
  for (const tick of scale.value.ticks) {
    if (!result.length || Math.abs(y(tick) - y(result[result.length - 1])) >= 12) result.push(tick)
  }
  return result
})

/** Отрезки, когда игрок был чемпионом: от боя, после которого пояс у него, до следующего боя. */
const championBands = computed(() => {
  const list = points.value
  const bands: { from: number; to: number }[] = []
  list.forEach((point, index) => {
    if (!point.champion) return
    const from = x(index)
    const to = index + 1 < list.length ? x(index + 1) : Math.max(x(index), PAD.left + plotWidth.value)
    const last = bands[bands.length - 1]
    if (last && Math.abs(last.to - from) < 0.5) last.to = to
    else bands.push({ from, to })
  })
  return bands
})

/** Бои, после которых игрок получил пояс: над точкой рисуется корона. */
const crowns = computed(() =>
  points.value
    .map((point, index) => ({ point, index }))
    .filter(({ point, index }) => inView(index) && point.item && point.champion && !point.item.champion_before),
)

const markers = computed(() =>
  points.value.map((point, index) => ({ point, index })).filter(({ point, index }) => point.item && inView(index)),
)

const showMarkers = computed(() => markers.value.length <= MAX_MARKERS)

/** Подписи дат: первый и последний бой в окне, по дате подтверждения — в этом порядке идут точки. */
const dateLabels = computed(() => {
  const shown = markers.value
  if (!shown.length) return []
  const first = shown[0]
  const last = shown[shown.length - 1]
  const labels = [{ index: first.index, text: formatShortDate(first.point.item!.confirmed_at), anchor: 'start' }]
  if (last.index !== first.index) labels.push({ index: last.index, text: formatShortDate(last.point.item!.confirmed_at), anchor: 'end' })
  return labels
})

function tickLabel(value: number): string {
  if (props.mode === 'points') return String(value)
  return value === CHAMPION_ROW ? 'Чемп.' : `№${value}`
}

function valueLabel(point: Point): string {
  if (props.mode === 'points') return `${point.value} ${plural(point.value, ['очко', 'очка', 'очков'])}`
  return point.value === CHAMPION_ROW ? 'Чемпион' : `№${point.value} в таблице`
}

// Указатели на графике: один — подсказка или перетаскивание, два пальца — масштаб.
const pointers = new Map<number, { x: number; startX: number }>()
let pinch: { distance: number; span: number; center: number } | null = null
let dragging = false

function localX(event: PointerEvent | WheelEvent, svg: Element): number {
  return event.clientX - svg.getBoundingClientRect().left
}

function indexAt(left: number): number {
  return viewStart.value + ((left - PAD.left) / plotWidth.value) * span.value
}

function pick(left: number): void {
  if (lastIndex.value === 0) {
    active.value = 0
    return
  }
  const index = Math.round(indexAt(left))
  active.value = Math.min(Math.ceil(viewEnd.value), Math.max(Math.floor(viewStart.value), index))
}

function onPointerDown(event: PointerEvent): void {
  const svg = event.currentTarget as Element
  const left = localX(event, svg)
  pointers.set(event.pointerId, { x: left, startX: left })
  dragging = false
  if (pointers.size === 2) {
    const [a, b] = [...pointers.values()]
    pinch = { distance: Math.abs(a.x - b.x) || 1, span: span.value, center: indexAt((a.x + b.x) / 2) }
    active.value = null
  } else {
    pick(left)
  }
  if (event.pointerType !== 'mouse') (svg as SVGElement).setPointerCapture?.(event.pointerId)
}

function onPointerMove(event: PointerEvent): void {
  const svg = event.currentTarget as Element
  const left = localX(event, svg)
  const pointer = pointers.get(event.pointerId)
  if (pointer && pinch && pointers.size === 2) {
    pointer.x = left
    const [a, b] = [...pointers.values()]
    const distance = Math.abs(a.x - b.x) || 1
    zoomAround(pinch.span * (pinch.distance / distance), pinch.center)
    return
  }
  // Перетаскивание: мышь с зажатой кнопкой или палец, пока график приближен.
  const pressed = pointer && (event.pointerType !== 'mouse' || event.buttons === 1)
  if (pressed && zoomed.value && (dragging || Math.abs(left - pointer.startX) > DRAG_THRESHOLD)) {
    dragging = true
    active.value = null
    panBy(((pointer.x - left) / plotWidth.value) * span.value)
    pointer.x = left
    return
  }
  if (pointer) pointer.x = left
  pick(left)
}

function onPointerUp(event: PointerEvent): void {
  pointers.delete(event.pointerId)
  if (pointers.size < 2) pinch = null
}

function onPointerLeave(event: PointerEvent): void {
  if (event.pointerType === 'mouse') {
    pointers.delete(event.pointerId)
    active.value = null
  }
}

/** Ctrl + колесо мыши или щипок на тачпаде; обычная прокрутка листает страницу. */
function onWheel(event: WheelEvent): void {
  if (!event.ctrlKey && !event.metaKey) return
  event.preventDefault()
  const center = indexAt(localX(event, event.currentTarget as Element))
  zoomAround(span.value * Math.exp(event.deltaY * 0.01), center)
}

const tooltip = computed(() => {
  if (active.value === null) return null
  const point = points.value[active.value]
  if (!point || !inView(active.value)) return null
  const left = Math.min(Math.max(x(active.value), 90), width.value - 90)
  const top = y(point.value)
  // У верхнего края подсказка уходит под точку, чтобы не вылезать за график.
  return { point, left, top, below: top < 80 }
})

const summary = computed(() => {
  const list = points.value
  if (!list.length) return ''
  const name = props.mode === 'points' ? 'Очки' : 'Место в таблице'
  return `${name}: было ${valueLabel(list[0])}, стало ${valueLabel(list[list.length - 1])}, боёв ${list.length - 1}`
})

const clipId = `chart-clip-${Math.random().toString(36).slice(2, 8)}`
</script>

<template>
  <div class="rating-chart-wrap">
    <div v-if="lastIndex > minSpan" class="chart-zoom" role="group" aria-label="Масштаб графика">
      <button type="button" class="btn sm" :disabled="span <= minSpan + 0.01" aria-label="Приблизить" @click="zoomIn">+</button>
      <button type="button" class="btn sm" :disabled="!zoomed" aria-label="Отдалить" @click="zoomOut">−</button>
      <button type="button" class="btn sm" :disabled="!zoomed" @click="resetView">Весь график</button>
      <span v-if="zoomed" class="small muted">Боёв на экране: {{ Math.round(span) }} из {{ lastIndex }}</span>
    </div>
    <div ref="box" class="rating-chart" :class="{ zoomed }">
      <svg
        v-if="points.length"
        :width="width"
        :height="HEIGHT"
        role="img"
        :aria-label="summary"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @pointerleave="onPointerLeave"
        @wheel="onWheel"
      >
        <defs>
          <clipPath :id="clipId">
            <rect :x="PAD.left" :y="0" :width="plotWidth" :height="HEIGHT" />
          </clipPath>
        </defs>
        <g :clip-path="`url(#${clipId})`">
          <rect
            v-for="band in championBands"
            :key="band.from"
            class="chart-champion"
            :x="band.from"
            :y="PAD.top"
            :width="Math.max(band.to - band.from, 2)"
            :height="plotHeight"
          />
        </g>
        <g class="chart-grid">
          <g v-for="tick in visibleTicks" :key="tick">
            <line :x1="PAD.left" :x2="PAD.left + plotWidth" :y1="y(tick)" :y2="y(tick)" />
            <text :x="PAD.left - 8" :y="y(tick)" text-anchor="end" dominant-baseline="middle">{{ tickLabel(tick) }}</text>
          </g>
        </g>
        <g class="chart-axis">
          <text
            v-for="label in dateLabels"
            :key="label.anchor"
            :x="label.anchor === 'start' ? Math.max(x(label.index), PAD.left) : Math.min(x(label.index), PAD.left + plotWidth)"
            :y="HEIGHT - 6"
            :text-anchor="label.anchor"
          >
            {{ label.text }}
          </text>
        </g>
        <g :clip-path="`url(#${clipId})`">
          <line
            v-if="tooltip"
            class="chart-cross"
            :x1="x(active!)"
            :x2="x(active!)"
            :y1="PAD.top"
            :y2="PAD.top + plotHeight"
          />
          <path class="chart-line" :d="path" />
        </g>
        <path
          v-for="crown in crowns"
          :key="`crown-${crown.index}`"
          class="chart-crown"
          :transform="`translate(${x(crown.index) - 8}, ${Math.max(y(crown.point.value) - 22, 0)})`"
          d="M1 11 L2.5 3 L6 7 L8 1 L10 7 L13.5 3 L15 11 Z M1.5 12.5 H14.5 V14.5 H1.5 Z"
        />
        <circle
          v-for="{ point, index } in markers"
          v-show="showMarkers || index === active"
          :key="index"
          class="chart-dot"
          :class="point.item!.won ? 'win' : 'loss'"
          :cx="x(index)"
          :cy="y(point.value)"
          :r="index === active ? 6 : 4"
        />
      </svg>
      <div v-if="tooltip" class="chart-tip" :class="{ below: tooltip.below }" :style="{ left: `${tooltip.left}px`, top: `${tooltip.top}px` }">
        <template v-if="tooltip.point.item">
          <span class="small muted">{{ formatBoutDate(tooltip.point.item.fought_at) }}</span>
          <span>
            <b :class="tooltip.point.item.won ? 'tone-plus' : 'tone-minus'">{{ tooltip.point.item.won ? 'Победа' : 'Поражение' }}</b>
            {{ tooltip.point.item.won ? 'над' : 'от' }} {{ tooltip.point.item.opponent.nickname }}
          </span>
          <span>{{ valueLabel(tooltip.point) }}<template v-if="mode === 'points'"> ({{ signed(tooltip.point.item.delta) }})</template></span>
          <span v-if="tooltip.point.champion && !tooltip.point.item.champion_before" class="tone-gold">Завоевал пояс чемпиона</span>
          <span v-else-if="tooltip.point.champion" class="tone-gold">С поясом чемпиона</span>
          <span v-else-if="tooltip.point.item.champion_before" class="tone-minus">Потерял пояс чемпиона</span>
        </template>
        <template v-else>
          <span class="small muted">До первого боя</span>
          <span>{{ valueLabel(tooltip.point) }}</span>
        </template>
      </div>
    </div>
  </div>
</template>
