<script setup lang="ts">
import { api } from '../api'
import StateBlock from '../components/StateBlock.vue'
import TournamentTile from '../components/TournamentTile.vue'
import { useLoad } from '../feedback'
import type { TournamentCard } from '../types'

const { data, error, loading, reload } = useLoad(() => api.get<TournamentCard[]>('/tournaments'))
</script>

<template>
  <main class="container page">
    <h1>Турниры</h1>
    <StateBlock :loading="loading" :error="error" skeleton="cards">
      <div v-if="data?.length" class="grid">
        <TournamentTile v-for="item in data" :key="item.id" :tournament="item" @changed="reload" />
      </div>
      <p v-else class="empty">Турниров пока нет.</p>
    </StateBlock>
  </main>
</template>
