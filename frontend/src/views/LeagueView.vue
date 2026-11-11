<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import BeltIcon from '../components/BeltIcon.vue'
import ChampionMark from '../components/ChampionMark.vue'
import PlayerChip from '../components/PlayerChip.vue'
import StateBlock from '../components/StateBlock.vue'
import { useLoad } from '../feedback'
import { plural } from '../format'
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

// Афиша чемпиона стоит над таблицей, пока не идёт поиск. При поиске чемпион — обычная строка с короной.
const champion = computed(() => (search.value.trim() ? undefined : data.value?.find((row) => row.is_champion && row.belt)))
const rows = computed(() => (champion.value ? data.value?.filter((row) => row !== champion.value) : data.value) ?? [])
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
    <StateBlock :loading="loading" :error="error" skeleton="league">
      <div v-if="data?.length" class="league-board">
        <section v-if="champion && champion.belt" class="champion-poster" aria-label="Чемпион лиги" data-tour="league-champion">
          <RouterLink class="poster-photo" :to="`/players/${champion.player.id}`" tabindex="-1" aria-hidden="true">
            <img v-if="champion.player.full_body_url" :src="champion.player.full_body_url" alt="" />
            <svg v-else class="poster-silhouette" viewBox="0 0 120 200" preserveAspectRatio="xMidYMax meet">
              <ellipse cx="60" cy="24" rx="12.5" ry="15" />
              <path d="M53 37h14l1 7c10 2 19 5 23 10 3 4 4 12 6 23l4 27c1 5-6 7-8 2l-8-26-3-12-3 25 2 18 4 30 1 33c0 4-11 4-11 0l-6-58-4-16-4 16-6 58c0 4-11 4-11 0l1-33 4-30 2-18-3-25-3 12-8 26c-2 5-9 3-8-2l4-27c2-11 3-19 6-23 4-5 13-8 23-10z" />
            </svg>
            <svg class="poster-edge" viewBox="0 0 100 100" preserveAspectRatio="none">
              <line x1="30" y1="0" x2="0" y2="100" vector-effect="non-scaling-stroke" />
            </svg>
          </RouterLink>
          <div class="poster-text">
            <div class="poster-label">
              <BeltIcon :belt="champion.belt" :size="34" />
              <span>Чемпион лиги</span>
            </div>
            <RouterLink class="poster-name" :class="{ long: champion.player.nickname.length > 14 }" :to="`/players/${champion.player.id}`">{{ champion.player.nickname }}</RouterLink>
            <div class="poster-stats">
              <span><b>{{ champion.points }}</b> {{ plural(champion.points, ['очко', 'очка', 'очков']) }}</span>
              <span>Рекорд <b>{{ champion.wins }}–{{ champion.losses }}</b></span>
            </div>
          </div>
        </section>
        <h2 v-if="champion" class="board-caption">Претенденты</h2>
        <div class="table-wrap" data-tour="league-table">
        <table class="fit-table">
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
            <tr v-for="row in rows" :key="row.player.id">
              <td class="num">
                <ChampionMark v-if="row.is_champion" />
                <span v-else class="place">№{{ row.display_place }}</span>
              </td>
              <td class="player-cell">
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
      </div>
      <p v-else class="empty">{{ search ? 'Игроки с таким ником не найдены.' : 'В лиге пока нет активных игроков.' }}</p>
    </StateBlock>
  </main>
</template>
