<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { api } from '../api'
import BeltIcon from '../components/BeltIcon.vue'
import PlayerChip from '../components/PlayerChip.vue'
import StateBlock from '../components/StateBlock.vue'
import { useLoad } from '../feedback'
import type { Belt } from '../types'

const { data, error, loading } = useLoad(() => api.get<Belt[]>('/belts'))
</script>

<template>
  <main class="container page">
    <h1>Пояса лиги</h1>
    <StateBlock :loading="loading" :error="error" skeleton="cards">
      <div class="grid">
        <article v-for="belt in data" :key="belt.id" class="card belt-row">
          <BeltIcon :belt="belt" :size="56" />
          <div class="stack" style="gap: 6px; min-width: 0">
            <RouterLink :to="`/belts/${belt.id}`"><h3>{{ belt.name }}</h3></RouterLink>
            <span class="small muted">{{ belt.kind === 'main' ? 'Основной пояс' : 'Турнирный пояс' }}</span>
            <PlayerChip v-if="belt.champion" :player="belt.champion" :size="24" />
            <span v-else class="small muted">Пояс вакантен</span>
          </div>
        </article>
      </div>
    </StateBlock>
  </main>
</template>
