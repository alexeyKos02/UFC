<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import FighterPhoto from './FighterPhoto.vue'
import ResultSubmit from './ResultSubmit.vue'
import { useAction } from '../feedback'
import { formatBoutDate } from '../format'
import type { Fighter, UpcomingBout } from '../types'

const props = defineProps<{ bout: UpcomingBout }>()
const emit = defineEmits<{ changed: [] }>()
const { busy, run } = useAction()

const caption = computed(() => {
  if (props.bout.kind === 'title') return 'Титульный бой'
  if (props.bout.kind === 'tournament') return `Турнирный бой · ${props.bout.round_name}`
  return 'Предстоящий бой'
})

const resultUrl = computed(() => {
  const { kind, id } = props.bout
  if (kind === 'title') return `/title-fights/${id}/result`
  if (kind === 'tournament') return `/tournaments/matches/${id}/result`
  return `/fights/planned/${id}/result`
})

const hasVotes = computed(() => props.bout.votes.first + props.bout.votes.second > 0)

async function vote(fighter: Fighter): Promise<void> {
  const { kind, id } = props.bout
  await run(() => api.put(`/fights/upcoming/${kind}/${id}/vote`, { player_id: fighter.id }), 'Голос учтён')
  emit('changed')
}

async function cancel(): Promise<void> {
  if (!window.confirm('Отменить запланированный бой?')) return
  await run(() => api.post(`/fights/planned/${props.bout.id}/cancel`), 'Бой отменён')
  emit('changed')
}
</script>

<template>
  <article class="bout">
    <div class="bout-main">
      <div class="bout-photo first">
        <FighterPhoto :fighter="bout.player1" side="first" />
      </div>

      <div class="bout-center">
        <p class="bout-caption">{{ caption }}</p>
        <div class="bout-names">
          <RouterLink class="bout-name first" :to="`/players/${bout.player1.id}`">{{ bout.player1.nickname }}</RouterLink>
          <span class="bout-vs">VS</span>
          <RouterLink class="bout-name second" :to="`/players/${bout.player2.id}`">{{ bout.player2.nickname }}</RouterLink>
        </div>
        <dl class="bout-facts bout-facts-single">
          <div><dt>Дата</dt><dd>{{ bout.scheduled_at ? formatBoutDate(bout.scheduled_at) : 'Не назначена' }}</dd></div>
        </dl>
        <RouterLink v-if="bout.tournament" class="link small" :to="`/tournaments/${bout.tournament.id}`">{{ bout.tournament.title }}</RouterLink>
      </div>

      <div class="bout-photo second">
        <FighterPhoto :fighter="bout.player2" side="second" />
      </div>
    </div>

    <div class="bout-vote-panel">
      <div class="duel">
        <div class="duel-head">
          <b>{{ bout.votes.first }}</b>
          <span class="duel-label">Голоса зрителей</span>
          <b>{{ bout.votes.second }}</b>
        </div>
        <div class="duel-bar" role="img" :aria-label="`Голоса: ${bout.player1.nickname} ${bout.votes.first}, ${bout.player2.nickname} ${bout.votes.second}`">
          <template v-if="hasVotes">
            <i v-if="bout.votes.first" class="corner-red" :style="{ flexGrow: bout.votes.first }" :title="`${bout.player1.nickname}: ${bout.votes.first}`"></i>
            <i v-if="bout.votes.second" class="corner-blue" :style="{ flexGrow: bout.votes.second }" :title="`${bout.player2.nickname}: ${bout.votes.second}`"></i>
          </template>
          <i v-else class="duel-neutral"></i>
        </div>
      </div>

      <div v-if="bout.can_vote" class="vote-choices">
        <button
          v-for="fighter in [bout.player1, bout.player2]"
          :key="fighter.id"
          class="btn"
          :class="{ 'vote-mine': bout.votes.my_vote === fighter.id }"
          :aria-pressed="bout.votes.my_vote === fighter.id"
          :disabled="busy"
          @click="vote(fighter)"
        >
          {{ bout.votes.my_vote === fighter.id ? `Ваш голос: ${fighter.nickname}` : `За бойца ${fighter.nickname}` }}
        </button>
      </div>
    </div>

    <div v-if="bout.can_submit || bout.can_cancel" class="bout-actions row">
      <ResultSubmit v-if="bout.can_submit" :url="resultUrl" :player1="bout.player1" :player2="bout.player2" @done="emit('changed')" />
      <button v-if="bout.can_cancel" class="btn danger" :disabled="busy" @click="cancel">Отменить бой</button>
    </div>
  </article>
</template>
