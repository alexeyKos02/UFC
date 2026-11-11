<script setup lang="ts">
import type { SkeletonKind } from '../types'
import SkeletonBlock from './SkeletonBlock.vue'

withDefaults(defineProps<{ loading: boolean; error: string; skeleton?: SkeletonKind }>(), { skeleton: 'list' })
</script>

<template>
  <SkeletonBlock v-if="loading" :kind="skeleton" />
  <p v-else-if="error" class="error-box">{{ error }}</p>
  <slot v-else />
</template>
