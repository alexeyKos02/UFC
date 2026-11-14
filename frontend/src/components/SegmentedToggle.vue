<script setup lang="ts" generic="T extends string">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

/**
 * Переключатель из нескольких кнопок в одной плашке. Подложка выбранной кнопки разгоняется
 * к новой кнопке и «желейно» сплющивается о неё, как о стенку: сжатие идёт от стороны удара,
 * поэтому подложка не выходит за свою кнопку и за края плашки. Без анимации, если система
 * просит меньше движения.
 */
const props = defineProps<{
  options: { value: T; label: string; count?: number }[]
  label: string
}>()
const model = defineModel<T>({ required: true })

const track = ref<HTMLElement | null>(null)
const buttons = ref<HTMLButtonElement[]>([])
const thumb = ref({ left: 0, width: 0 })
const jelly = ref(false)
// С какой стороны подложка ударяется о новую кнопку: туда смещается точка сжатия.
const hitSide = ref<'left' | 'right'>('right')
const ready = ref(false)
let observer: ResizeObserver | null = null
// Удар ждёт, пока подложка доедет: так сжатие идёт ровно о новую кнопку, а не по дороге.
let hitPending = false
let hitFallback: number | undefined

function hit(): void {
  hitPending = false
  window.clearTimeout(hitFallback)
  // Перезапуск анимации: снять класс, дать браузеру кадр и поставить снова.
  jelly.value = false
  requestAnimationFrame(() => (jelly.value = true))
}

function onTransitionEnd(event: TransitionEvent): void {
  if (event.propertyName === 'translate' && hitPending) hit()
}

function place(): void {
  const index = props.options.findIndex((option) => option.value === model.value)
  const button = buttons.value[index]
  if (!button) return
  thumb.value = { left: button.offsetLeft, width: button.offsetWidth }
}

onMounted(() => {
  place()
  // Первая расстановка без анимации, дальше подложка переезжает.
  requestAnimationFrame(() => (ready.value = true))
  if (track.value) {
    observer = new ResizeObserver(place)
    observer.observe(track.value)
  }
})
onBeforeUnmount(() => {
  observer?.disconnect()
  window.clearTimeout(hitFallback)
})

watch(model, async (next, previous) => {
  const index = (value: T) => props.options.findIndex((option) => option.value === value)
  hitSide.value = index(next) > index(previous) ? 'right' : 'left'
  jelly.value = false
  hitPending = true
  await nextTick()
  place()
  // Если подложка не сдвинулась (или переходы отключены), события конца переезда не будет.
  window.clearTimeout(hitFallback)
  hitFallback = window.setTimeout(() => hitPending && hit(), 450)
})
watch(() => props.options.map((option) => `${option.label}${option.count ?? ''}`).join('|'), () => nextTick(place))
</script>

<template>
  <div ref="track" class="segmented" role="group" :aria-label="label">
    <span
      class="segmented-thumb"
      :class="[{ ready, jelly }, `hit-${hitSide}`]"
      :style="{ translate: `${thumb.left}px 0`, width: `${thumb.width}px` }"
      aria-hidden="true"
      @animationend="jelly = false"
      @transitionend="onTransitionEnd"
    ></span>
    <button
      v-for="option in options"
      :key="option.value"
      ref="buttons"
      type="button"
      :aria-pressed="model === option.value"
      @click="model = option.value"
    >
      {{ option.label }}
      <span v-if="option.count !== undefined" class="segmented-count">{{ option.count }}</span>
    </button>
  </div>
</template>
