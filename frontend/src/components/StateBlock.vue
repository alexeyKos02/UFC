<script setup lang="ts">
defineProps<{ loading: boolean; error: string }>()
</script>

<template>
  <p v-if="loading" class="muted">Загрузка…</p>
  <p v-else-if="error" class="error-box">{{ error }}</p>
  <slot v-else />
</template>
