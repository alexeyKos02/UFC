<script setup lang="ts">
import { computed } from 'vue'
import { fightStatusLabel, matchStateLabel, titleStatusLabel, tournamentStatusLabel } from '../format'
import type { FightStatus, MatchState, TitleFightStatus, TournamentStatus } from '../types'

const props = defineProps<{
  fight?: FightStatus
  tournament?: TournamentStatus
  match?: MatchState
  title?: TitleFightStatus
}>()

const TONES: Record<string, string> = {
  pending: 'tone-amber',
  disputed: 'tone-red',
  confirmed: 'tone-green',
  cancelled: 'tone-grey',
  deleted: 'tone-red',
  draft: 'tone-grey',
  registration: 'tone-blue',
  in_progress: 'tone-amber',
  finished: 'tone-green',
  bye: 'tone-grey',
  completed: 'tone-green',
  ready: 'tone-blue',
  waiting_players: 'tone-grey',
  scheduled: 'tone-blue',
}

const value = computed(() => props.fight ?? props.tournament ?? props.match ?? props.title ?? 'draft')
const label = computed(() => {
  if (props.fight) return fightStatusLabel[props.fight]
  if (props.tournament) return tournamentStatusLabel[props.tournament]
  if (props.match) return matchStateLabel[props.match]
  if (props.title) return titleStatusLabel[props.title]
  return ''
})
</script>

<template>
  <span class="badge" :class="TONES[value]">{{ label }}</span>
</template>
