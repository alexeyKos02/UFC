<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'
import { useAction } from '../feedback'
import PlayerChip from './PlayerChip.vue'
import type { MatchOut } from '../types'

/**
 * Техническая победа в матче турнира (для админа и владельца): выбрать, кто проходит дальше,
 * и указать причину. Боя нет — исход не идёт в статистику и очки лиги.
 */
const props = defineProps<{ match: MatchOut }>()
const emit = defineEmits<{ done: [] }>()

const { busy, run } = useAction()
const winnerId = ref<number | null>(null)
const reason = ref('Соперник не явился')

async function submit(): Promise<void> {
  if (winnerId.value === null) return
  const body = { winner_id: winnerId.value, reason: reason.value }
  if (await run(() => api.post(`/admin/tournaments/matches/${props.match.id}/walkover`, body), 'Техническая победа присуждена')) {
    emit('done')
  }
}
</script>

<template>
  <form class="stack" @submit.prevent="submit">
    <p class="small muted">
      {{ match.round_name }}. Победитель проходит дальше без боя: исход не попадёт в статистику и очки лиги.
      <template v-if="match.state === 'pending' || match.state === 'disputed'">Записанный результат матча будет отменён.</template>
    </p>
    <fieldset class="walkover-choice">
      <legend class="small muted">Кто проходит дальше</legend>
      <label v-for="player in [match.player1, match.player2]" :key="player!.id" class="walkover-option">
        <input v-model="winnerId" type="radio" name="walkover-winner" :value="player!.id" required />
        <PlayerChip :player="player!" :size="24" />
      </label>
    </fieldset>
    <label class="field">
      Причина
      <textarea v-model="reason" required minlength="3" maxlength="500"></textarea>
    </label>
    <button class="btn primary" type="submit" :disabled="busy || winnerId === null">Присудить техническую победу</button>
  </form>
</template>
