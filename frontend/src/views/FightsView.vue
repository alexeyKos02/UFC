<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import FightCard from '../components/FightCard.vue'
import { errorText } from '../feedback'
import type { FightBrief, FightKind } from '../types'

const PAGE = 30
const kind = ref<FightKind | ''>('')
const items = ref<FightBrief[]>([])
const total = ref(0)
const loading = ref(true)
const problem = ref('')

async function load(reset: boolean): Promise<void> {
  loading.value = true
  try {
    const offset = reset ? 0 : items.value.length
    const filter = kind.value ? `&kind=${kind.value}` : ''
    const page = await api.get<{ items: FightBrief[]; total: number }>(`/fights?limit=${PAGE}&offset=${offset}${filter}`)
    items.value = reset ? page.items : [...items.value, ...page.items]
    total.value = page.total
    problem.value = ''
  } catch (error) {
    problem.value = errorText(error)
  } finally {
    loading.value = false
  }
}

watch(kind, () => void load(true))
void load(true)
</script>

<template>
  <main class="container page">
    <div class="page-head">
      <h1>Бои лиги</h1>
      <div class="row">
        <select v-model="kind" aria-label="Тип боя" style="width: auto">
          <option value="">Все типы</option>
          <option value="regular">Обычные</option>
          <option value="tournament">Турнирные</option>
          <option value="title">Титульные</option>
        </select>
        <RouterLink class="btn primary" to="/fights/new">Записать бой</RouterLink>
      </div>
    </div>
    <p v-if="problem" class="error-box">{{ problem }}</p>
    <div v-if="items.length" class="grid">
      <FightCard v-for="fight in items" :key="fight.id" :fight="fight" />
    </div>
    <p v-else-if="!loading && !problem" class="empty">Подтверждённых боёв пока нет.</p>
    <p v-if="loading" class="muted">Загрузка…</p>
    <button v-if="items.length < total && !loading" class="btn" style="align-self: center" @click="load(false)">Показать ещё</button>
  </main>
</template>
