<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { api } from '../api'
import BeltIcon from '../components/BeltIcon.vue'
import PlayerChip from '../components/PlayerChip.vue'
import StateBlock from '../components/StateBlock.vue'
import { useLoad } from '../feedback'
import { formatDate } from '../format'
import type { BeltDetail } from '../types'

const props = defineProps<{ id: string }>()
const { data, error, loading } = useLoad(() => api.get<BeltDetail>(`/belts/${props.id}`))
</script>

<template>
  <main class="container page">
    <StateBlock :loading="loading" :error="error">
      <template v-if="data">
        <div class="belt-row">
          <BeltIcon :belt="data" :size="72" />
          <div class="stack" style="gap: 4px">
            <h1>{{ data.name }}</h1>
            <span class="muted">{{ data.kind === 'main' ? 'Основной пояс' : 'Турнирный пояс' }}</span>
          </div>
        </div>
        <section class="section">
          <h2>Действующий чемпион</h2>
          <div v-if="data.champion" class="winner-banner">
            <BeltIcon :belt="data" :size="52" />
            <div class="stack" style="gap: 4px">
              <span class="kicker" style="color: var(--gold)">Действующий чемпион</span>
              <PlayerChip :player="data.champion" :size="32" />
            </div>
          </div>
          <p v-else class="empty">Пояс вакантен.</p>
        </section>
        <section class="section">
          <h2>История победителей</h2>
          <div v-if="data.history.length" class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Победитель</th>
                  <th>Где выигран</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="win in data.history" :key="win.id">
                  <td class="small">{{ formatDate(win.won_at) }}</td>
                  <td>
                    <div class="row" style="gap: 6px">
                      <PlayerChip :player="win.player" :size="24" />
                      <span v-if="win.is_defense" class="badge plain tone-gold">Защита</span>
                    </div>
                  </td>
                  <td class="small">
                    <RouterLink v-if="win.tournament" class="link" :to="`/tournaments/${win.tournament.id}`">{{ win.tournament.title }}</RouterLink>
                    <RouterLink v-else class="link" :to="`/fights/${win.fight_id}`">Титульный бой #{{ win.fight_id }}</RouterLink>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="empty">Этот пояс ещё никто не выигрывал.</p>
        </section>
      </template>
    </StateBlock>
  </main>
</template>
