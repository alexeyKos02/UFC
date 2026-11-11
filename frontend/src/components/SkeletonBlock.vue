<script setup lang="ts">
/** Заготовка страницы, пока грузятся данные: серые блоки в форме будущего содержимого. */
import type { SkeletonKind } from '../types'

withDefaults(defineProps<{ kind?: SkeletonKind; count?: number }>(), { kind: 'list', count: 0 })
</script>

<template>
  <div class="skeleton" :class="`skeleton-${kind}`" role="status" aria-busy="true">
    <span class="sr-hidden">Загрузка…</span>

    <template v-if="kind === 'table' || kind === 'league'">
      <div v-if="kind === 'league'" class="sk sk-poster" />
      <div class="sk-table">
        <div v-for="row in count || 8" :key="row" class="sk-row">
          <div class="sk sk-num" />
          <div class="sk sk-avatar" />
          <div class="sk sk-line" :style="{ width: `${40 + ((row * 17) % 35)}%` }" />
          <div class="sk sk-num" />
        </div>
      </div>
    </template>

    <div v-else-if="kind === 'cards'" class="grid">
      <div v-for="card in count || 6" :key="card" class="card stack">
        <div class="sk" style="height: 120px" />
        <div class="sk sk-line" style="width: 70%" />
        <div class="sk sk-line" style="width: 45%" />
      </div>
    </div>

    <div v-else-if="kind === 'list'" class="stack" style="gap: 16px">
      <div v-for="card in count || 3" :key="card" class="card stack">
        <div class="row between">
          <div class="sk sk-figure" />
          <div class="stack" style="flex: 1; align-items: center; gap: 8px">
            <div class="sk sk-line" style="width: 40%" />
            <div class="sk sk-title" style="width: 70%" />
            <div class="sk sk-line" style="width: 50%" />
          </div>
          <div class="sk sk-figure" />
        </div>
      </div>
    </div>

    <div v-else-if="kind === 'profile'" class="profile-top">
      <div class="sk sk-photo" />
      <div class="stack" style="gap: 16px">
        <div class="sk sk-title" style="width: 55%" />
        <div class="tiles">
          <div v-for="tile in 3" :key="tile" class="sk" style="height: 72px" />
        </div>
        <div class="sk" style="height: 14px" />
        <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr))">
          <div class="sk" style="height: 110px" />
          <div class="sk" style="height: 110px" />
        </div>
      </div>
    </div>

    <div v-else-if="kind === 'fight'" class="stack" style="gap: 16px">
      <div class="card stack">
        <div class="row between">
          <div class="sk sk-figure tall" />
          <div class="stack" style="flex: 1; align-items: center; gap: 10px">
            <div class="sk sk-line" style="width: 30%" />
            <div class="sk sk-title" style="width: 80%" />
            <div class="sk sk-line" style="width: 55%" />
          </div>
          <div class="sk sk-figure tall" />
        </div>
      </div>
      <div class="sk" style="height: 160px" />
    </div>

    <div v-else class="card stack">
      <div class="sk" style="height: 44px" />
      <div class="sk sk-line" style="width: 25%" />
      <div class="sk" style="height: 40px" />
      <div class="sk" style="height: 40px; width: 50%" />
    </div>
  </div>
</template>
