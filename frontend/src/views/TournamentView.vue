<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { currentUser } from '../auth'
import BeltIcon from '../components/BeltIcon.vue'
import PlayerChip from '../components/PlayerChip.vue'
import ResultSubmit from '../components/ResultSubmit.vue'
import StateBlock from '../components/StateBlock.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAction, useLoad } from '../feedback'
import { isFull, seatsLine } from '../format'
import type { MatchOut, PlayerBrief, TournamentDetail } from '../types'

const props = defineProps<{ id: string }>()
const { data, error, loading, reload } = useLoad(() => api.get<TournamentDetail>(`/tournaments/${props.id}`))
const { busy, run } = useAction()

const isRegistration = computed(() => data.value?.status === 'registration')

async function join(): Promise<void> {
  await run(() => api.post(`/tournaments/${props.id}/join`), 'Вы в турнире')
  await reload()
}

async function leave(): Promise<void> {
  await run(() => api.post(`/tournaments/${props.id}/leave`), 'Вы отказались от участия')
  await reload()
}

function isMine(match: MatchOut): boolean {
  return [match.player1?.id, match.player2?.id].includes(currentUser.value?.id)
}

function slots(match: MatchOut): (PlayerBrief | null)[] {
  return [match.player1, match.player2]
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
              <span v-if="data.win_points" class="small muted">Очки за победу: +{{ data.win_points }}</span>
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
          <div class="bracket">
            <section v-for="round in data.rounds" :key="round.round" class="bracket-round">
              <h3>{{ round.name }}</h3>
              <div class="bracket-matches">
                <article v-for="match in round.matches" :key="match.id" class="match" :class="{ mine: isMine(match) && match.state !== 'completed' && match.state !== 'bye' }">
                  <div v-for="(slot, index) in slots(match)" :key="index" class="match-player">
                    <PlayerChip v-if="slot" :player="slot" :size="24" :class="{ 'is-loser': match.winner_id && match.winner_id !== slot.id }" />
                    <span v-else class="tbd small">{{ match.is_bye ? 'Без соперника' : 'Определится позже' }}</span>
                    <span v-if="slot && match.winner_id === slot.id" class="winner-mark">{{ match.is_bye ? 'Проход' : 'Победа' }}</span>
                  </div>
                  <div class="match-foot">
                    <StatusBadge :match="match.state" />
                    <ResultSubmit
                      v-if="match.can_submit && match.player1 && match.player2"
                      compact
                      :url="`/tournaments/matches/${match.id}/result`"
                      :player1="match.player1"
                      :player2="match.player2"
                      @done="reload"
                    />
                    <RouterLink v-else-if="match.fight_id && (isMine(match) || match.state === 'completed')" class="link small" :to="`/fights/${match.fight_id}`">Открыть бой</RouterLink>
                  </div>
                </article>
              </div>
            </section>
          </div>
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
