<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import BeltIcon from '../components/BeltIcon.vue'
import PlayerChip from '../components/PlayerChip.vue'
import StateBlock from '../components/StateBlock.vue'
import StatusBadge from '../components/StatusBadge.vue'
import TournamentBracket from '../components/TournamentBracket.vue'
import { useAction, useLoad } from '../feedback'
import { isFull, seatsLine } from '../format'
import type { TournamentDetail } from '../types'

const props = defineProps<{ id: string }>()
const { data, error, loading, reload } = useLoad(() => api.get<TournamentDetail>(`/tournaments/${props.id}`))
const { busy, run } = useAction()

const isRegistration = computed(() => data.value?.status === 'registration')

/** Призы в очки лиги за места; бои турнира сами очков лиги не дают. */
const prizeLine = computed(() => {
  const tournament = data.value
  if (!tournament) return ''
  const parts = [
    tournament.win_points ? `1-е +${tournament.win_points}` : '',
    tournament.second_points ? `2-е +${tournament.second_points}` : '',
    tournament.third_points ? `3-е +${tournament.third_points}${tournament.has_third_place ? '' : ' каждому полуфиналисту'}` : '',
  ].filter(Boolean)
  return parts.length ? `Призы в очки лиги: ${parts.join(' · ')}` : ''
})

async function join(): Promise<void> {
  await run(() => api.post(`/tournaments/${props.id}/join`), 'Вы в турнире')
  await reload()
}

async function leave(): Promise<void> {
  await run(() => api.post(`/tournaments/${props.id}/leave`), 'Вы отказались от участия')
  await reload()
}
</script>

<template>
  <main class="container page">
    <StateBlock :loading="loading" :error="error" skeleton="list">
      <template v-if="data">
        <div class="belt-row">
          <BeltIcon :belt="data.belt" :size="64" />
          <div class="stack" style="gap: 4px">
            <h1>{{ data.title }}</h1>
            <div class="row">
              <StatusBadge :tournament="data.status" />
              <RouterLink class="link small" :to="`/belts/${data.belt.id}`">За пояс «{{ data.belt.name }}»</RouterLink>
              <span class="small muted">Мест занято: {{ seatsLine(data) }}</span>
              <span v-if="prizeLine" class="small muted">{{ prizeLine }}</span>
            </div>
          </div>
        </div>
        <p v-if="data.description" class="muted">{{ data.description }}</p>

        <div v-if="data.winner" class="winner-banner">
          <BeltIcon :belt="data.belt" :size="52" />
          <div class="stack" style="gap: 4px">
            <span class="kicker" style="color: var(--gold)">Победитель турнира</span>
            <PlayerChip :player="data.winner" :size="32" />
          </div>
        </div>
        <p v-if="data.status === 'cancelled'" class="error-box">Турнир отменён. Причина: {{ data.cancel_reason }}</p>

        <div v-if="isRegistration" class="row">
          <button v-if="!data.is_participant && !isFull(data)" class="btn primary" :disabled="busy" @click="join">Вступить</button>
          <button v-if="!data.is_participant && isFull(data)" class="btn" disabled>Мест нет</button>
          <template v-if="data.is_participant">
            <span class="badge tone-green">Вы участвуете</span>
            <button class="btn" :disabled="busy" @click="leave">Отказаться</button>
          </template>
        </div>

        <section v-if="data.rounds.length" class="section">
          <h2>Сетка</h2>
          <TournamentBracket :rounds="data.rounds" :running="data.status === 'in_progress'" @changed="reload" />
        </section>

        <section class="section">
          <h2>Участники</h2>
          <div v-if="data.participants.length" class="row">
            <span v-for="player in data.participants" :key="player.id" class="card" style="padding: 6px 10px; max-width: 100%">
              <PlayerChip :player="player" :size="24" />
            </span>
          </div>
          <p v-else class="empty">Пока никто не записался.</p>
        </section>
      </template>
    </StateBlock>
  </main>
</template>
