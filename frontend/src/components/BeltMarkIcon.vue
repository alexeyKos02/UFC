<script setup lang="ts">
import { CROWN_PATH, CROWN_SLASH_PATH, SHIELD_CHECK_PATH, SHIELD_PATH, type BeltMark } from '../beltMarks'

/**
 * Значок события с основным поясом в квадрате 16×16 — группа SVG.
 * На графике ставится через transform, в легенде — внутри своего <svg viewBox="0 0 16 16">.
 */
defineProps<{ mark: BeltMark }>()
</script>

<template>
  <g class="belt-mark" :class="mark">
    <template v-if="mark === 'defend'">
      <path class="belt-mark-fill" :d="SHIELD_PATH" />
      <path class="belt-mark-cut" :d="SHIELD_CHECK_PATH" />
    </template>
    <template v-else>
      <path class="belt-mark-fill" :d="CROWN_PATH" />
      <template v-if="mark === 'lose'">
        <path class="belt-mark-cut" :d="CROWN_SLASH_PATH" />
        <path class="belt-mark-slash" :d="CROWN_SLASH_PATH" />
      </template>
    </template>
  </g>
</template>
