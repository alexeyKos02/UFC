<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api } from '../api'
import BeltIcon from './BeltIcon.vue'
import PlayerChip from './PlayerChip.vue'
import StatusBadge from './StatusBadge.vue'
import { useAction } from '../feedback'
import { isFull, seatsLine, tournamentCta } from '../format'
import type { TournamentCard } from '../types'

const props = defineProps<{ tournament: TournamentCard }>()
const emit = defineEmits<{ changed: [] }>()
const router = useRouter()
const { busy, run } = useAction()

const fill = computed(() => Math.min(100, (props.tournament.seats_taken / props.tournament.capacity) * 100))
const canJoin = computed(
  () => props.tournament.status === 'registration' && !props.tournament.is_participant && !isFull(props.tournament),
)
const canLeave = computed(() => props.tournament.status === 'registration' && props.tournament.is_participant)
const isFullClosed = computed(
  () => props.tournament.status === 'registration' && !props.tournament.is_participant && isFull(props.tournament),
)

async function join(): Promise<void> {
  await run(() => api.post(`/tournaments/${props.tournament.id}/join`), 'Вы в турнире')
  // Счётчик обновляется и после отказа: последнее место мог занять другой игрок.
  emit('changed')
}

async function leave(): Promise<void> {
  if (await run(() => api.post(`/tournaments/${props.tournament.id}/leave`), 'Вы отказались от участия')) emit('changed')
}

function open(): void {
  void router.push(`/tournaments/${props.tournament.id}`)
}
</script>

<template>
  <article class="card tournament-card">
    <div class="row between">
      <StatusBadge :tournament="tournament.status" />
      <span class="small muted">Мест занято: {{ seatsLine(tournament) }}</span>
    </div>
    <div class="belt-row">
      <BeltIcon :belt="tournament.belt" />
      <div>
        <h3><RouterLink :to="`/tournaments/${tournament.id}`">{{ tournament.title }}</RouterLink></h3>
        <p class="small muted">За пояс «{{ tournament.belt.name }}»</p>
      </div>
    </div>
    <div v-if="tournament.status === 'registration'" class="seats" aria-hidden="true">
      <span :style="{ width: `${fill}%` }"></span>
    </div>
    <p v-if="tournament.description" class="small muted">{{ tournament.description }}</p>
    <div v-if="tournament.winner" class="row small">
      <span class="muted">Победитель:</span>
      <PlayerChip :player="tournament.winner" :size="22" />
    </div>
    <div class="row" style="margin-top: auto">
      <button v-if="canJoin" class="btn primary" :disabled="busy" @click="join">Вступить</button>
      <button v-if="isFullClosed" class="btn" disabled>Мест нет</button>
      <template v-if="canLeave">
        <span class="badge tone-green">Вы участвуете</span>
        <button class="btn sm" :disabled="busy" @click="leave">Отказаться</button>
      </template>
      <button v-if="tournament.status !== 'registration'" class="btn" @click="open">{{ tournamentCta(tournament) }}</button>
      <RouterLink v-else class="link small" :to="`/tournaments/${tournament.id}`">Подробнее</RouterLink>
    </div>
  </article>
</template>
