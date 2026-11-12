<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { signed } from '../format'
import type { Fighter } from '../types'

/** delta — на сколько очков изменился рейтинг бойца за этот бой; не передаётся, пока очков нет. */
defineProps<{ fighter: Fighter; winner?: boolean; side: 'first' | 'second'; delta?: number | null }>()
</script>

<template>
  <RouterLink class="fighter-photo" :to="`/players/${fighter.id}`">
    <img v-if="fighter.full_body_url" :src="fighter.full_body_url" :alt="fighter.nickname" />
    <svg v-else viewBox="0 0 120 200" preserveAspectRatio="xMidYMin slice" role="img" :aria-label="`${fighter.nickname}: фото не загружено`">
      <g fill="#3a3f4a">
        <ellipse cx="60" cy="24" rx="12.5" ry="15" />
        <path d="M53 37h14l1 7c10 2 19 5 23 10 3 4 4 12 6 23l4 27c1 5-6 7-8 2l-8-26-3-12-3 25 2 18 4 30 1 33c0 4-11 4-11 0l-6-58-4-16-4 16-6 58c0 4-11 4-11 0l1-33 4-30 2-18-3-25-3 12-8 26c-2 5-9 3-8-2l4-27c2-11 3-19 6-23 4-5 13-8 23-10z" />
      </g>
    </svg>
    <span v-if="winner" class="win-tag" :class="side">Победа</span>
    <span
      v-if="delta !== undefined && delta !== null"
      class="photo-delta"
      :class="[side, delta > 0 ? 'tone-plus' : delta < 0 ? 'tone-minus' : '']"
      :aria-label="`Очки за бой: ${signed(delta)}`"
    >{{ signed(delta) }}</span>
  </RouterLink>
</template>
