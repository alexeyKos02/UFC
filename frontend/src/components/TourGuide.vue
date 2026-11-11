<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { closeOnboarding } from '../onboarding'

/**
 * Тур по сайту: сам открывает нужные страницы, подсвечивает элементы и показывает подсказку рядом с ними.
 * target — CSS-селекторы по порядку предпочтения, берётся первый видимый элемент.
 * Шаг без target — карточка по центру экрана.
 */
interface TourStep {
  title: string
  text: string
  route?: string
  target?: string[]
  /** Если элемента на странице нет (например, пояс вакантен), шаг пропускается. */
  optional?: boolean
}

const steps: TourStep[] = [
  {
    title: 'Добро пожаловать в Лигу UFC',
    text: 'Покажем на самом сайте, как записать бой, что делать, если бой записал соперник, и где смотреть рейтинг. Это займёт минуту.',
  },
  {
    title: 'Записать бой',
    text: 'Сыграли — нажмите эту кнопку в разделе «Бои». Будущий бой тоже можно записать заранее.',
    route: '/fights',
    target: ['[data-tour="new-fight"]'],
  },
  {
    title: 'Бой прошёл или ещё впереди',
    text: '«Бой уже прошёл» — сразу вносите результат. «Бой ещё не состоялся» — бой появится в предстоящих, зрители смогут проголосовать, а результат вы внесёте после игры.',
    route: '/fights/new',
    target: ['[data-tour="fight-mode"]'],
  },
  {
    title: 'Соперник и результат',
    text: 'Выберите соперника, затем победителя. Способ победы и раунд — по желанию. Нажмите «Отправить и подтвердить»: запись уйдёт сопернику, а очки начислятся, когда он её подтвердит.',
    route: '/fights/new',
    target: ['[data-tour="fight-opponent"]'],
  },
  {
    title: 'Если бой записал соперник',
    text: 'Здесь загорится красный счётчик: значит, кто-то записал бой с вами и ждёт вашего ответа.',
    route: '/my-fights',
    target: ['[data-tour="nav-my-fights"]'],
  },
  {
    title: 'На подтверждение',
    text: '«Подтвердить» — бой засчитан, очки и статистика обновятся сразу. «Оспорить» — напишите, что не так: соперник исправит запись, и вы подтвердите новую версию. Пока вы не ответили, бой не считается.',
    route: '/my-fights',
    target: ['[data-tour="to-confirm"] .bout-actions', '[data-tour="to-confirm"]'],
  },
  {
    title: 'Ваши записи',
    text: 'Здесь бои, которые записали вы и которые ждут ответа соперника. Если он оспорит запись, она окажется в «Оспоренных» — исправьте её там.',
    route: '/my-fights',
    target: ['[data-tour="waiting"]'],
  },
  {
    title: 'Чемпион лиги',
    text: 'Сверху таблицы — чемпион с основным поясом. Забрать пояс можно в титульном бою.',
    route: '/league',
    target: ['[data-tour="league-champion"]'],
    optional: true,
  },
  {
    title: 'Таблица лиги',
    text: 'Претенденты идут по очкам Elo. Все стартуют с 1000: победа над сильным даёт больше очков, над слабым — меньше, проигравший теряет столько же.',
    route: '/league',
    target: ['[data-tour="league-table"]'],
  },
  {
    title: 'Готово',
    text: 'Удачных боёв! Вернуться к подсказкам можно в меню — пункт «Как это работает».',
  },
]

const route = useRoute()
const router = useRouter()
const index = ref(0)
const ready = ref(false)
const spot = ref<{ top: number; left: number; width: number; height: number } | null>(null)
const card = ref<HTMLElement | null>(null)
const cardSize = ref({ width: 0, height: 0 })
const viewport = ref({ width: window.innerWidth, height: window.innerHeight })
const step = computed(() => steps[index.value])
const last = computed(() => index.value === steps.length - 1)

let target: HTMLElement | null = null
let showToken = 0
let frame = 0

const PAD = 6
const GAP = 12
const MARGIN = 12
/** Высота липкой шапки сайта: подсвеченный элемент не должен прятаться под ней. */
const HEADER = 64

function visible(element: Element): boolean {
  const rect = element.getBoundingClientRect()
  return rect.width > 0 && rect.height > 0
}

function findTarget(selectors: string[]): HTMLElement | null {
  for (const selector of selectors) {
    const found = [...document.querySelectorAll<HTMLElement>(selector)].find(visible)
    if (found) return found
  }
  return null
}

// Страницы грузят данные после перехода, поэтому элемент ищем несколько секунд.
async function waitForTarget(selectors: string[], token: number): Promise<HTMLElement | null> {
  for (let attempt = 0; attempt < 40; attempt++) {
    if (token !== showToken) return null
    const element = findTarget(selectors)
    if (element) return element
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  return null
}

function scrollToTarget(element: HTMLElement): void {
  // Шапка прилипает к верху экрана: её элементы видны всегда, страницу показываем с начала.
  if (element.closest('.header')) {
    window.scrollTo({ top: 0, behavior: 'auto' })
    return
  }
  const rect = element.getBoundingClientRect()
  const room = window.innerHeight - HEADER
  // Высокий блок показываем с начала, небольшой — посередине свободной части экрана.
  const offset = rect.height > room * 0.5 ? HEADER + 16 : HEADER + (room - rect.height) / 3
  window.scrollTo({ top: Math.max(0, window.scrollY + rect.top - offset), behavior: 'auto' })
}

function measure(): void {
  viewport.value = { width: window.innerWidth, height: window.innerHeight }
  if (card.value) cardSize.value = { width: card.value.offsetWidth, height: card.value.offsetHeight }
  if (!target || !target.isConnected) {
    spot.value = null
    return
  }
  const rect = target.getBoundingClientRect()
  // Подсветка не выше половины экрана: у длинных таблиц и списков видно начало.
  const height = Math.min(rect.height, window.innerHeight * 0.5)
  spot.value = { top: rect.top - PAD, left: rect.left - PAD, width: rect.width + PAD * 2, height: height + PAD * 2 }
}

function scheduleMeasure(): void {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(measure)
}

async function show(next: number, direction: 1 | -1 = 1): Promise<void> {
  const token = ++showToken
  const wanted = steps[next]
  if (!wanted) return
  ready.value = false
  target = null
  spot.value = null
  if (wanted.route && route.path !== wanted.route) await router.push(wanted.route)
  if (wanted.target) {
    const element = await waitForTarget(wanted.target, token)
    if (token !== showToken) return
    if (!element && wanted.optional) {
      const skipTo = next + direction
      if (skipTo >= 0 && skipTo < steps.length) return show(skipTo, direction)
    }
    target = element
    if (element) scrollToTarget(element)
  }
  index.value = next
  ready.value = true
  await nextTick()
  measure()
  card.value?.querySelector<HTMLElement>('h2')?.focus()
}

const spotStyle = computed(() =>
  spot.value
    ? {
        top: `${spot.value.top}px`,
        left: `${spot.value.left}px`,
        width: `${spot.value.width}px`,
        height: `${spot.value.height}px`,
      }
    : {},
)

// Карточка встаёт под подсветкой или над ней, а если места нет — внизу экрана.
const cardStyle = computed(() => {
  const { width: vw, height: vh } = viewport.value
  const width = Math.min(380, vw - MARGIN * 2)
  if (!spot.value) return { width: `${width}px`, top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
  const height = cardSize.value.height || 220
  const left = Math.min(Math.max(spot.value.left + spot.value.width / 2 - width / 2, MARGIN), vw - width - MARGIN)
  const below = spot.value.top + spot.value.height + GAP
  if (below + height <= vh - MARGIN) return { width: `${width}px`, top: `${below}px`, left: `${left}px` }
  const above = spot.value.top - GAP - height
  if (above >= HEADER) return { width: `${width}px`, top: `${above}px`, left: `${left}px` }
  return { width: `${width}px`, bottom: `${MARGIN}px`, left: `${(vw - width) / 2}px` }
})

async function finish(to?: string): Promise<void> {
  showToken++
  await closeOnboarding()
  if (to) void router.push(to)
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') void finish()
  if (event.key === 'ArrowRight' && !last.value) void show(index.value + 1, 1)
  if (event.key === 'ArrowLeft' && index.value > 0) void show(index.value - 1, -1)
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
  window.addEventListener('resize', scheduleMeasure)
  window.addEventListener('scroll', scheduleMeasure, true)
  void show(0)
})
onUnmounted(() => {
  showToken++
  cancelAnimationFrame(frame)
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', scheduleMeasure)
  window.removeEventListener('scroll', scheduleMeasure, true)
})
</script>

<template>
  <Teleport to="body">
    <div class="tour">
      <!-- Ловит нажатия: во время тура страница только показывается. -->
      <div class="tour-blocker" :class="{ dim: !spot }" @click.stop />
      <div v-if="spot" class="tour-spot" :style="spotStyle" />
      <div
        v-show="ready"
        ref="card"
        class="tour-card"
        role="dialog"
        aria-modal="true"
        :aria-label="step.title"
        :style="cardStyle"
      >
        <div class="tour-head">
          <span class="small muted">{{ index + 1 }} из {{ steps.length }}</span>
          <button class="icon-btn" aria-label="Закрыть подсказки" @click="finish()">×</button>
        </div>
        <h2 tabindex="-1">{{ step.title }}</h2>
        <p>{{ step.text }}</p>
        <div class="tour-dots" aria-hidden="true">
          <span v-for="(_, dot) in steps" :key="dot" :class="{ on: dot === index }" />
        </div>
        <div class="tour-actions">
          <button v-if="index > 0" class="btn sm" @click="show(index - 1, -1)">Назад</button>
          <button v-else class="btn sm" @click="finish()">Пропустить</button>
          <button v-if="last" class="btn sm" @click="finish('/fights/new')">Записать бой</button>
          <button v-if="!last" class="btn sm primary" @click="show(index + 1, 1)">Далее</button>
          <button v-else class="btn sm primary" @click="finish()">Готово</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
