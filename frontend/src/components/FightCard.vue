<script setup lang="ts">
import { RouterLink } from 'vue-router'
import FightActions from './FightActions.vue'
import PlayerChip from './PlayerChip.vue'
import StatusBadge from './StatusBadge.vue'
import { fightKindLabel, formatDateTime, resultLine } from '../format'
import type { FightBrief } from '../types'

defineProps<{ fight: FightBrief; actions?: boolean }>()
const emit = defineEmits<{ changed: [] }>()
</script>

<template>
  <article class="card stack">
    <div class="row between">
      <div class="row small muted">
        <span>{{ formatDateTime(fight.fought_at) }}</span>
        <span>· {{ fightKindLabel[fight.kind] }}</span>
        <RouterLink v-if="fight.tournament" class="link" :to="`/tournaments/${fight.tournament.id}`">{{ fight.tournament.title }}</RouterLink>
      </div>
      <StatusBadge :fight="fight.status" />
    </div>
    <div class="fight-row">
      <div class="stack" style="gap: 2px; min-width: 0">
        <PlayerChip :player="fight.player1" />
        <span v-if="fight.winner_id === fight.player1.id" class="winner-mark">Победитель</span>
      </div>
      <span class="versus">VS</span>
      <div class="stack" style="gap: 2px; min-width: 0; align-items: flex-end">
        <PlayerChip :player="fight.player2" />
        <span v-if="fight.winner_id === fight.player2.id" class="winner-mark">Победитель</span>
      </div>
    </div>
    <div class="row between">
      <span class="small muted">{{ resultLine(fight.method, fight.round) || 'Способ победы не указан' }}</span>
      <RouterLink class="link small" :to="`/fights/${fight.id}`">Открыть бой</RouterLink>
    </div>
    <p v-if="fight.dispute_reason" class="small tone-red">Причина спора: {{ fight.dispute_reason }}</p>
    <FightActions v-if="actions" :fight="fight" @changed="emit('changed')" />
  </article>
</template>
