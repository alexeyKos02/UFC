<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { formatBoutDate, formatShortDate, plural, signed } from '../format'
import type { RatingHistoryPoint } from '../types'

/**
 * График очков или номера в таблице по боям игрока. По оси X — бои по порядку,
 * первая точка — значение до первого показанного боя. Наведение или касание показывает бой.
 */
const props = defineProps<{ history: RatingHistoryPoint[]; mode: 'points' | 'place' }>()

const HEIGHT = 220
const PAD = { top: 14, right: 14, bottom: 26, left: 46 }
// Чемпион стоит над №1: на шкале мест у него своя строка над единицей.
const CHAMPION_ROW = 0
// Точки рисуются, пока они не сливаются; при большем числе боёв видна только выбранная.
const MAX_MARKERS = 50

const box = ref<HTMLElement | null>(null)
const width = ref(600)
const active = ref<number | null>(null)
let observer: ResizeObserver | null = null

onMounted(() => {
  if (!box.value) return
  width.value = box.value.clientWidth
  observer = new ResizeObserver(([entry]) => {
    width.value = entry.contentRect.width
  })
  observer.observe(box.value)
})
onBeforeUnmount(() => observer?.disconnect())

interface Point {
  value: number
  item: RatingHistoryPoint | null
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
    { value: start, item: null },
    ...items.map((item) => ({
      value: props.mode === 'points' ? item.points_after : placeValue(item.table_place_after, item.champion_after),
      item,
    })),
  ]
})

const plotWidth = computed(() => Math.max(width.value - PAD.left - PAD.right, 10))
const plotHeight = HEIGHT - PAD.top - PAD.bottom

/** Шкала Y: для очков — с запасом и «круглыми» делениями, для мест — целые номера, №1 сверху. */
const scale = computed(() => {
  const values = points.value.map((point) => point.value)
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
  const span = Math.max(high - low, 20)
  const step = [5, 10, 20, 25, 50, 100, 200].find((candidate) => span / candidate <= 5) ?? 500
  low = Math.floor((low - span * 0.08) / step) * step
  high = Math.ceil((high + span * 0.08) / step) * step
  const ticks: number[] = []
  for (let value = low; value <= high; value += step) ticks.push(value)
  return { low, high, ticks }
})

function x(index: number): number {
  const count = points.value.length
  return PAD.left + (count < 2 ? plotWidth.value / 2 : (index / (count - 1)) * plotWidth.value)
}

function y(value: number): number {
  const { low, high } = scale.value
  const share = high === low ? 0.5 : (value - low) / (high - low)
  // Для очков больше — выше; для мест меньший номер — выше.
  return props.mode === 'points' ? PAD.top + (1 - share) * plotHeight : PAD.top + share * plotHeight
}

const path = computed(() => {
  const list = points.value
  if (!list.length) return ''
  let line = `M${x(0)},${y(list[0].value)}`
  for (let index = 1; index < list.length; index += 1) {
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

function tickLabel(value: number): string {
  if (props.mode === 'points') return String(value)
  return value === CHAMPION_ROW ? 'Чемп.' : `№${value}`
}

function valueLabel(point: Point): string {
  if (props.mode === 'points') return `${point.value} ${plural(point.value, ['очко', 'очка', 'очков'])}`
  return point.value === CHAMPION_ROW ? 'Чемпион' : `№${point.value} в таблице`
}

const showMarkers = computed(() => points.value.length <= MAX_MARKERS)

function pick(event: PointerEvent): void {
  const svg = event.currentTarget as SVGElement
  const left = event.clientX - svg.getBoundingClientRect().left
  const count = points.value.length
  if (count < 2) {
    active.value = 0
    return
  }
  const index = Math.round(((left - PAD.left) / plotWidth.value) * (count - 1))
  active.value = Math.min(count - 1, Math.max(0, index))
}

const tooltip = computed(() => {
  if (active.value === null) return null
  const point = points.value[active.value]
  if (!point) return null
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
</script>

<template>
  <div ref="box" class="rating-chart">
    <svg
      v-if="points.length"
      :width="width"
      :height="HEIGHT"
      role="img"
      :aria-label="summary"
      @pointermove="pick"
      @pointerdown="pick"
      @pointerleave="active = null"
    >
      <g class="chart-grid">
        <g v-for="tick in visibleTicks" :key="tick">
          <line :x1="PAD.left" :x2="PAD.left + plotWidth" :y1="y(tick)" :y2="y(tick)" />
          <text :x="PAD.left - 8" :y="y(tick)" text-anchor="end" dominant-baseline="middle">{{ tickLabel(tick) }}</text>
        </g>
      </g>
      <g class="chart-axis">
        <text v-if="points[1]?.item" :x="x(1)" :y="HEIGHT - 6" text-anchor="start">{{ formatShortDate(points[1].item!.fought_at) }}</text>
        <text v-if="points.length > 2" :x="x(points.length - 1)" :y="HEIGHT - 6" text-anchor="end">
          {{ formatShortDate(points[points.length - 1].item!.fought_at) }}
        </text>
      </g>
      <line
        v-if="tooltip"
        class="chart-cross"
        :x1="x(active!)"
        :x2="x(active!)"
        :y1="PAD.top"
        :y2="PAD.top + plotHeight"
      />
      <path class="chart-line" :d="path" />
      <g v-for="(point, index) in points" :key="index">
        <circle
          v-if="point.item && (showMarkers || index === active)"
          class="chart-dot"
          :class="point.item.won ? 'win' : 'loss'"
          :cx="x(index)"
          :cy="y(point.value)"
          :r="index === active ? 6 : 4"
        />
      </g>
    </svg>
    <div v-if="tooltip" class="chart-tip" :class="{ below: tooltip.below }" :style="{ left: `${tooltip.left}px`, top: `${tooltip.top}px` }">
      <template v-if="tooltip.point.item">
        <span class="small muted">{{ formatBoutDate(tooltip.point.item.fought_at) }}</span>
        <span>
          <b :class="tooltip.point.item.won ? 'tone-plus' : 'tone-minus'">{{ tooltip.point.item.won ? 'Победа' : 'Поражение' }}</b>
          {{ tooltip.point.item.won ? 'над' : 'от' }} {{ tooltip.point.item.opponent.nickname }}
        </span>
        <span>{{ valueLabel(tooltip.point) }}<template v-if="mode === 'points'"> ({{ signed(tooltip.point.item.delta) }})</template></span>
      </template>
      <template v-else>
        <span class="small muted">До первого боя</span>
        <span>{{ valueLabel(tooltip.point) }}</span>
      </template>
    </div>
  </div>
</template>
