<script setup lang="ts">
withDefaults(defineProps<{ url: string | null; size?: number; alt?: string }>(), { size: 32, alt: '' })
</script>

<template>
  <img v-if="url" class="avatar" :src="url" :alt="alt" :width="size" :height="size" :style="{ width: `${size}px`, height: `${size}px` }" />
  <svg v-else class="avatar" viewBox="0 0 40 40" :width="size" :height="size" role="img" :aria-label="alt || 'Нет аватара'">
    <rect width="40" height="40" fill="#2a2e37" />
    <circle cx="20" cy="15" r="7" fill="#6b7280" />
    <path d="M6 40c1-11 7-16 14-16s13 5 14 16z" fill="#6b7280" />
  </svg>
</template>
