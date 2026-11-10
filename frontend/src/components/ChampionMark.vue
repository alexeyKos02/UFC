<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 22 })
</script>

<template>
  <svg class="champion-mark" viewBox="0 0 24 24" :width="size" :height="size" role="img" aria-label="Чемпион">
    <title>Чемпион</title>
    <path fill="currentColor" d="M3 7.5l4.6 3.9L12 4l4.4 7.4L21 7.5 19.3 17H4.7z" />
    <rect fill="currentColor" x="4.7" y="18.5" width="14.6" height="2.2" rx="1.1" />
  </svg>
</template>
