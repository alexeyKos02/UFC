<script setup lang="ts">
import { computed } from 'vue'
import type { BeltBrief } from '../types'

const props = withDefaults(defineProps<{ belt: BeltBrief; past?: boolean; size?: number }>(), { past: false, size: 44 })
const metal = computed(() => (props.past ? '#8a8f99' : props.belt.kind === 'main' ? '#f2c542' : '#e0a93a'))
const strap = computed(() => (props.past ? '#50545d' : '#7a2230'))
</script>

<template>
  <img
    v-if="belt.icon_url"
    class="belt-icon"
    :class="{ past }"
    :src="belt.icon_url"
    :alt="`Пояс ${belt.name}`"
    :width="size"
    :height="size"
  />
  <svg v-else class="belt-icon" viewBox="0 0 48 48" :width="size" :height="size" role="img" :aria-label="`Пояс ${belt.name}`">
    <rect x="1" y="17" width="46" height="14" rx="4" :fill="strap" />
    <circle cx="24" cy="24" r="14" :fill="metal" />
    <circle cx="24" cy="24" r="10.5" fill="none" stroke="#00000055" stroke-width="1.5" />
    <path d="M24 16.5l2.3 4.8 5.2.7-3.8 3.6.9 5.2-4.6-2.5-4.6 2.5.9-5.2-3.8-3.6 5.2-.7z" fill="#00000066" />
    <circle cx="6.5" cy="24" r="3" :fill="metal" />
    <circle cx="41.5" cy="24" r="3" :fill="metal" />
  </svg>
</template>
