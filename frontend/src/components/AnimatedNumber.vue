<script setup lang="ts">
import { ref, watch } from 'vue'

/**
 * Число, которое при смене значения не «считает», а заменяется: старое уезжает и гаснет,
 * новое въезжает на его место. Больше — снизу вверх, меньше — сверху вниз.
 */
const props = defineProps<{ value: number }>()

const direction = ref<'up' | 'down'>('up')
watch(
  () => props.value,
  (next, previous) => {
    direction.value = next >= previous ? 'up' : 'down'
  },
)
</script>

<template>
  <span class="anum">
    <Transition :name="`anum-${direction}`">
      <span :key="value" class="anum-value">{{ value }}</span>
    </Transition>
  </span>
</template>
