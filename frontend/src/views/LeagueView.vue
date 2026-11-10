<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import ChampionMark from '../components/ChampionMark.vue'
import PlayerChip from '../components/PlayerChip.vue'
import StateBlock from '../components/StateBlock.vue'
import { useLoad } from '../feedback'
import type { LeagueRow } from '../types'

const search = ref('')
const { data, error, loading, reload } = useLoad(() =>
  api.get<LeagueRow[]>(`/players?q=${encodeURIComponent(search.value.trim())}`),
)

let timer = 0
watch(search, () => {
  window.clearTimeout(timer)
  timer = window.setTimeout(() => void reload(), 250)
})
onUnmounted(() => window.clearTimeout(timer))
</script>

<template>
  <main class="container page">
    <div class="page-head">
      <h1>Игроки и рейтинг</h1>
      <label class="field" style="width: min(100%, 300px)">
        <span class="sr-hidden">Поиск по нику</span>
        <input v-model="search" type="search" placeholder="Поиск по нику" />
      </label>
    </div>
    <StateBlock :loading="loading" :error="error">
      <div v-if="data?.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="num">Место</th>
              <th>Игрок</th>
              <th class="num">Очки</th>
              <th class="num hide-sm">Бои</th>
              <th class="num hide-sm">Победы</th>
              <th class="num hide-sm">Поражения</th>
              <th class="num hide-sm">% побед</th>
              <th class="num show-sm-cell">Поб–пор</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in data" :key="row.player.id">
              <td class="num">
                <ChampionMark v-if="row.is_champion" />
                <span v-else class="place">№{{ row.display_place }}</span>
              </td>
              <td>
                <div class="row" style="gap: 6px">
                  <PlayerChip :player="row.player" />
                  <span v-if="row.is_special" class="badge plain tone-gold">Спецместо</span>
                </div>
              </td>
              <td class="num">{{ row.points }}</td>
              <td class="num hide-sm">{{ row.fights }}</td>
              <td class="num hide-sm">{{ row.wins }}</td>
              <td class="num hide-sm">{{ row.losses }}</td>
              <td class="num hide-sm">{{ row.win_rate === null ? '—' : `${row.win_rate}%` }}</td>
              <td class="num show-sm-cell">{{ row.wins }}–{{ row.losses }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="empty">{{ search ? 'Игроки с таким ником не найдены.' : 'В лиге пока нет активных игроков.' }}</p>
    </StateBlock>
  </main>
</template>
