<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import BracketMatch from './BracketMatch.vue'
import SegmentedToggle from './SegmentedToggle.vue'
import type { MatchOut, RoundOut } from '../types'

/**
 * Турнирная сетка. На компьютере круги идут колонками, матчи соединены линиями от пары к матчу
 * следующего круга, матч за 3-е место — под финалом. На телефоне круги переключаются плашкой
 * (как статистика в профиле), матчи круга идут списком.
 */
const props = defineProps<{ rounds: RoundOut[]; running: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const MOBILE_QUERY = '(max-width: 760px)'
// Отступ матча за 3-е место от финала (вместе с подписью над ним).
const THIRD_GAP = 28

const roundsCount = computed(() => Math.max(0, ...props.rounds.map((round) => round.round)))
const mainMatches = (round: RoundOut) => round.matches.filter((match) => !match.is_third_place)
const thirdPlace = computed(() =>
  props.rounds.flatMap((round) => round.matches).find((match) => match.is_third_place) ?? null,
)

function matchAt(roundNo: number, position: number): MatchOut | undefined {
  return props.rounds
    .find((round) => round.round === roundNo)
    ?.matches.find((match) => match.position === position && !match.is_third_place)
}

/** Название матча в списке на телефоне: «Полуфинал 1», «Финал», «За 3-е место». */
function matchTitle(round: RoundOut, match: MatchOut): string {
  if (match.is_third_place) return 'За 3-е место'
  if (round.round === roundsCount.value) return 'Финал'
  return `${round.name} ${match.position + 1}`
}

// Телефон или компьютер: рисуется только одна раскладка.
const isMobile = ref(false)
let media: MediaQueryList | null = null
const syncMedia = () => (isMobile.value = media?.matches ?? false)

// Круг на телефоне: по умолчанию тот, где сейчас идут бои.
const tabs = computed(() =>
  props.rounds.map((round) => {
    const left = roundsCount.value - round.round
    const short = props.rounds.length > 3
    const label = left === 0 ? 'Финал' : left === 1 ? (short ? '1/2' : 'Полуфинал') : `1/${2 ** left}${short ? '' : ' финала'}`
    return { value: String(round.round), label }
  }),
)
const activeRound = ref('1')
function pickActiveRound(): void {
  const live = props.rounds.find((round) =>
    round.matches.some((match) => ['ready', 'pending', 'disputed'].includes(match.state)),
  )
  activeRound.value = String((live ?? props.rounds[props.rounds.length - 1])?.round ?? 1)
}
const shownRound = computed(() => props.rounds.find((round) => String(round.round) === activeRound.value))

// Линии между кругами: от правого края матча к левому краю матча следующего круга, с изломом посередине.
// Матч за 3-е место ставится под финал по его реальному положению; если не помещается, сетка вытягивается вниз.
const canvas = ref<HTMLElement | null>(null)
const thirdBox = ref<HTMLElement | null>(null)
const lines = ref<string[]>([])
const size = ref({ width: 0, height: 0 })
const thirdPos = ref({ top: 0, left: 0, width: 0 })
const extraBottom = ref(0)
let observer: ResizeObserver | null = null

function drawLines(): void {
  const root = canvas.value
  if (!root) return
  const base = root.getBoundingClientRect()
  const boxOf = (id: number) => root.querySelector(`[data-match-id="${id}"]`)?.getBoundingClientRect()
  const paths: string[] = []
  for (const round of props.rounds) {
    if (round.round === 1) continue
    for (const match of mainMatches(round)) {
      const target = boxOf(match.id)
      if (!target) continue
      for (const seat of [0, 1]) {
        const feeder = matchAt(round.round - 1, match.position * 2 + seat)
        const from = feeder && boxOf(feeder.id)
        if (!from) continue
        const x1 = from.right - base.left
        const y1 = from.top + from.height / 2 - base.top
        const x2 = target.left - base.left
        const y2 = target.top + target.height / 2 - base.top
        const middle = Math.round((x1 + x2) / 2)
        paths.push(`M${x1},${y1} H${middle} V${y2} H${x2}`)
      }
    }
  }
  lines.value = paths

  const final = matchAt(roundsCount.value, 0)
  const finalBox = final && boxOf(final.id)
  if (thirdPlace.value && finalBox) {
    const top = finalBox.bottom - base.top + THIRD_GAP
    thirdPos.value = { top, left: finalBox.left - base.left, width: finalBox.width }
    const thirdHeight = thirdBox.value?.offsetHeight ?? 0
    const contentHeight = root.offsetHeight - extraBottom.value
    extraBottom.value = Math.max(0, Math.ceil(top + thirdHeight - contentHeight))
  } else {
    extraBottom.value = 0
  }
  size.value = { width: root.scrollWidth, height: root.scrollHeight }
}

async function redraw(): Promise<void> {
  await nextTick()
  if (!isMobile.value) drawLines()
}

onMounted(() => {
  media = window.matchMedia(MOBILE_QUERY)
  syncMedia()
  media.addEventListener('change', syncMedia)
  pickActiveRound()
  redraw()
})
onBeforeUnmount(() => {
  media?.removeEventListener('change', syncMedia)
  observer?.disconnect()
})

watch(canvas, (element) => {
  observer?.disconnect()
  if (!element) return
  observer = new ResizeObserver(() => drawLines())
  observer.observe(element)
})
watch(() => props.rounds, redraw, { deep: true })
watch(isMobile, redraw)
</script>

<template>
  <div
      v-if="!isMobile"
      ref="canvas"
      class="bracket"
      :style="{ '--bracket-rounds': rounds.length, paddingBottom: `${extraBottom}px` }"
    >
      <svg class="bracket-lines" :width="size.width" :height="size.height" aria-hidden="true">
        <path v-for="(line, index) in lines" :key="index" :d="line" />
      </svg>
      <section v-for="round in rounds" :key="round.round" class="bracket-round">
        <h3>{{ round.name }}</h3>
        <div class="bracket-matches">
          <div v-for="match in mainMatches(round)" :key="match.id" class="bracket-slot">
            <BracketMatch :match="match" :tournament-running="running" @done="emit('changed')" />
          </div>
        </div>
      </section>
      <div
        v-if="thirdPlace"
        ref="thirdBox"
        class="bracket-third"
        :style="{ top: `${thirdPos.top}px`, left: `${thirdPos.left}px`, width: `${thirdPos.width}px` }"
      >
        <h3>Матч за 3-е место</h3>
        <BracketMatch :match="thirdPlace" :tournament-running="running" @done="emit('changed')" />
      </div>
  </div>

  <div v-else class="bracket-mobile stack">
    <SegmentedToggle v-model="activeRound" label="Круг турнира" :options="tabs" />
    <template v-if="shownRound">
      <div v-for="match in shownRound.matches" :key="match.id" class="bracket-mobile-item">
        <h3>{{ matchTitle(shownRound, match) }}</h3>
        <BracketMatch :match="match" :tournament-running="running" @done="emit('changed')" />
      </div>
      <p v-if="shownRound.round !== roundsCount" class="small muted">
        {{ thirdPlace ? 'Финал и матч за 3-е место — во вкладке «Финал»' : 'Финал — во вкладке «Финал»' }}
      </p>
    </template>
  </div>
</template>
