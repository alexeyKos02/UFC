<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { currentUser } from '../auth'
import PlayerChip from './PlayerChip.vue'
import ResultSubmit from './ResultSubmit.vue'
import StatusBadge from './StatusBadge.vue'
import type { MatchOut, PlayerBrief } from '../types'

/** Карточка матча турнирной сетки: игроки с отметкой победителя, состояние и действие. */
const props = defineProps<{ match: MatchOut; tournamentRunning: boolean }>()
const emit = defineEmits<{ done: [] }>()

const slots = computed<(PlayerBrief | null)[]>(() => [props.match.player1, props.match.player2])
const isMine = computed(() => slots.value.some((player) => player && player.id === currentUser.value?.id))
</script>

<template>
  <article
    class="match"
    :class="{ mine: isMine && tournamentRunning && match.state !== 'completed' && match.state !== 'bye' }"
    :data-match-id="match.id"
  >
    <div v-for="(slot, index) in slots" :key="index" class="match-player">
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
        @done="emit('done')"
      />
      <RouterLink v-else-if="match.fight_id && (isMine || match.state === 'completed')" class="link small" :to="`/fights/${match.fight_id}`">Открыть бой</RouterLink>
    </div>
  </article>
</template>
