<script setup lang="ts">
import { CUP_BASE_PATH, CUP_BOWL_PATH, CUP_HANDLES_PATH, type PrizePlace } from '../beltMarks'

/**
 * Кубок за место в турнире в квадрате 16×16 — группа SVG: золотой, серебряный или бронзовый
 * с цифрой места. Отличается от короны и щита основного пояса.
 * На графике ставится через transform, в легенде — внутри своего <svg viewBox="0 0 16 16">.
 */
defineProps<{ place: PrizePlace }>()
</script>

<template>
  <g class="prize-cup" :class="`place-${place}`">
    <path class="prize-cup-handles" :d="CUP_HANDLES_PATH" />
    <path class="prize-cup-fill" :d="CUP_BOWL_PATH" />
    <path class="prize-cup-fill" :d="CUP_BASE_PATH" />
    <text class="prize-cup-digit" x="8" y="5.6" text-anchor="middle" dominant-baseline="middle">{{ place }}</text>
  </g>
</template>
