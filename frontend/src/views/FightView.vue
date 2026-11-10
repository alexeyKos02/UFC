<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import FightActions from '../components/FightActions.vue'
import PlayerChip from '../components/PlayerChip.vue'
import StateBlock from '../components/StateBlock.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useLoad } from '../feedback'
import { fightKindLabel, formatDateTime, resultLine, signed } from '../format'
import type { FightDetail } from '../types'

const props = defineProps<{ id: string }>()
const { data, error, loading, reload } = useLoad(() => api.get<FightDetail>(`/fights/${props.id}`))

const winnerName = computed(() => {
  if (!data.value) return ''
  return data.value.winner_id === data.value.player1.id ? data.value.player1.nickname : data.value.player2.nickname
})
const loserId = computed(() => {
  if (!data.value) return 0
  return data.value.winner_id === data.value.player1.id ? data.value.player2.id : data.value.player1.id
})

function manualFor(playerId: number): number | null {
  const adjustment = data.value?.adjustment
  if (!adjustment || !data.value) return null
  return playerId === loserId.value ? adjustment.loser_delta : adjustment.winner_delta
}
</script>

<template>
  <main class="container page">
    <StateBlock :loading="loading" :error="error">
      <template v-if="data">
        <div class="page-head">
          <div class="stack" style="gap: 6px">
            <h1>Бой #{{ data.id }}</h1>
            <div class="row small muted">
              <StatusBadge :fight="data.status" />
              <span>{{ fightKindLabel[data.kind] }}</span>
              <RouterLink v-if="data.tournament" class="link" :to="`/tournaments/${data.tournament.id}`">{{ data.tournament.title }}</RouterLink>
              <span v-if="data.is_title_defense === true">Защита пояса</span>
              <span>Версия {{ data.version_no }}</span>
            </div>
          </div>
        </div>

        <section class="card stack">
          <div class="fight-row">
            <PlayerChip :player="data.player1" :size="44" />
            <span class="versus">VS</span>
            <div class="right"><PlayerChip :player="data.player2" :size="44" /></div>
          </div>
          <p><b>Победитель: {{ winnerName }}</b></p>
          <p class="muted">{{ formatDateTime(data.fought_at) }}<template v-if="resultLine(data.method, data.round)"> · {{ resultLine(data.method, data.round) }}</template></p>
          <p v-if="data.dispute_reason" class="tone-red">Причина спора: {{ data.dispute_reason }}</p>
          <FightActions :fight="data" @changed="reload" />
        </section>

        <section v-if="data.rating_changes.length" class="section">
          <h2>Рейтинг</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Игрок</th>
                  <th class="num">Место до боя</th>
                  <th class="num">Очки до</th>
                  <th class="num">Автоматически</th>
                  <th class="num">Вручную</th>
                  <th class="num">Очки после боя</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="change in data.rating_changes" :key="change.player.id">
                  <td><PlayerChip :player="change.player" :size="24" /></td>
                  <td class="num">№{{ change.place_before }}</td>
                  <td class="num">{{ change.points_before }}</td>
                  <td class="num"><span :class="change.delta > 0 ? 'delta-up' : 'delta-down'">{{ signed(change.delta) }}</span></td>
                  <td class="num">{{ manualFor(change.player.id) === null ? '—' : signed(manualFor(change.player.id) ?? 0) }}</td>
                  <td class="num">{{ change.points_after }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="data.adjustment" class="preview">Причина ручной корректировки: {{ data.adjustment.reason }}</p>
        </section>

        <section class="section">
          <h2>История версий</h2>
          <div class="stack">
            <article v-for="version in [...data.versions].reverse()" :key="version.version_no" class="card stack">
              <div class="row between">
                <b>Версия {{ version.version_no }}<template v-if="version.version_no === data.version_no"> (текущая)</template></b>
                <span class="small muted">{{ formatDateTime(version.created_at) }}</span>
              </div>
              <p class="small">
                Победитель: {{ version.winner.nickname }}. Бой: {{ formatDateTime(version.fought_at) }}<template v-if="resultLine(version.method, version.round)">. {{ resultLine(version.method, version.round) }}</template>.
              </p>
              <p class="small muted">
                Внёс: {{ version.submitted_by.nickname }}. Подтвердили: {{ version.confirmed_by.map((player) => player.nickname).join(', ') || 'никто' }}.
              </p>
              <p v-if="version.dispute_reason" class="small tone-red">
                Оспорил {{ version.disputed_by?.nickname }}: {{ version.dispute_reason }}
              </p>
            </article>
          </div>
        </section>
      </template>
    </StateBlock>
  </main>
</template>
