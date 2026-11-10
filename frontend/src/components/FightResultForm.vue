<script setup lang="ts">
import { ref } from 'vue'
import { fromLocalInput, toLocalInput } from '../format'
import type { FightMethod, PlayerBrief, ResultPayload } from '../types'

const props = defineProps<{
  player1: PlayerBrief
  player2: PlayerBrief
  initial?: { fought_at: string; winner_id: number; method: FightMethod | null; round: number | null }
  busy?: boolean
}>()
const emit = defineEmits<{ submit: [payload: ResultPayload] }>()

const foughtAt = ref(toLocalInput(props.initial?.fought_at ?? new Date()))
const winnerId = ref<number | null>(props.initial?.winner_id ?? null)
const method = ref<FightMethod | ''>(props.initial?.method ?? '')
const round = ref<number | ''>(props.initial?.round ?? '')
const problem = ref('')

function submit(): void {
  if (winnerId.value === null) {
    problem.value = 'Выберите победителя'
    return
  }
  if (!foughtAt.value) {
    problem.value = 'Укажите дату и время боя'
    return
  }
  problem.value = ''
  emit('submit', {
    fought_at: fromLocalInput(foughtAt.value),
    winner_id: winnerId.value,
    method: method.value || null,
    round: round.value || null,
  })
}
</script>

<template>
  <form class="stack" @submit.prevent="submit">
    <fieldset class="stack" style="border: 0; padding: 0; margin: 0">
      <legend class="small muted" style="padding: 0; margin-bottom: 6px">Победитель</legend>
      <div class="choice-group">
        <label v-for="player in [player1, player2]" :key="player.id" class="choice">
          <input v-model="winnerId" type="radio" name="winner" :value="player.id" />
          {{ player.nickname }}
        </label>
      </div>
    </fieldset>
    <label class="field">
      Дата и время боя
      <input v-model="foughtAt" type="datetime-local" required />
    </label>
    <div class="field-grid">
      <label class="field">
        Способ победы (необязательно)
        <select v-model="method">
          <option value="">Не указан</option>
          <option value="ko_tko">KO/TKO</option>
          <option value="submission">Сабмишен</option>
          <option value="decision">Решение</option>
        </select>
      </label>
      <label class="field">
        Раунд (необязательно)
        <select v-model.number="round">
          <option value="">Не указан</option>
          <option v-for="value in 5" :key="value" :value="value">{{ value }}</option>
        </select>
      </label>
    </div>
    <p v-if="problem" class="small tone-red">{{ problem }}</p>
    <button class="btn primary" type="submit" :disabled="busy">Отправить и подтвердить</button>
  </form>
</template>
