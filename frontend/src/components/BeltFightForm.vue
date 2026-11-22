<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api'
import { useAction } from '../feedback'
import { beltPointsLine, fromLocalInput } from '../format'
import type { Belt, PlayerBrief, ResultPayload } from '../types'
import FightResultForm from './FightResultForm.vue'

/**
 * Бой за пояс для админа и владельца. «record» — как «Записать бой»: пара, победитель, дата,
 * способ, раунд; бой сразу засчитан, пояс у победителя. «schedule» — назначить бой заранее.
 * У пояса с чемпионом первый боец — чемпион. Используется на странице пояса и в «Админке → Пояса».
 */
const props = defineProps<{ belt: Belt; players: PlayerBrief[]; mode: 'record' | 'schedule' }>()
const emit = defineEmits<{ done: [] }>()
const { busy, run } = useAction()

const champion = computed(() => props.belt.champion)
const player1 = ref<number | ''>('')
const player2 = ref<number | ''>('')
const scheduledAt = ref('')

const pair = computed<[PlayerBrief, PlayerBrief] | null>(() => {
  const first = champion.value ?? props.players.find((player) => player.id === player1.value)
  const second = props.players.find((player) => player.id === player2.value)
  return first && second && first.id !== second.id ? [first, second] : null
})

const pointsHint = computed(() =>
  props.belt.kind !== 'main' && props.belt.title_points
    ? `Очки по Elo, плюс за пояс: ${beltPointsLine(props.belt.title_points).toLowerCase()}.`
    : 'Очки по Elo, как за обычный бой.',
)

async function record(payload: ResultPayload): Promise<void> {
  if (!pair.value) return
  const body = { ...payload, player1_id: pair.value[0].id, player2_id: pair.value[1].id }
  if (await run(() => api.post(`/admin/belts/${props.belt.id}/fights`, body), 'Бой за пояс записан')) emit('done')
}

async function schedule(): Promise<void> {
  if (!pair.value) return
  const body = {
    belt_id: props.belt.id,
    player1_id: pair.value[0].id,
    player2_id: pair.value[1].id,
    scheduled_at: scheduledAt.value ? fromLocalInput(scheduledAt.value) : null,
  }
  if (await run(() => api.post('/admin/title-fights', body), 'Бой за пояс назначен')) emit('done')
}
</script>

<template>
  <div class="stack">
    <div class="field-grid">
      <label v-if="!champion" class="field">
        Первый игрок
        <select v-model.number="player1" required>
          <option value="" disabled>Выберите игрока</option>
          <option v-for="player in players" :key="player.id" :value="player.id" :disabled="player.id === player2">{{ player.nickname }}</option>
        </select>
      </label>
      <label v-else class="field">
        Чемпион
        <input :value="champion.nickname" disabled />
      </label>
      <label class="field">
        {{ champion ? 'Претендент' : 'Второй игрок' }}
        <select v-model.number="player2" required>
          <option value="" disabled>Выберите игрока</option>
          <option v-for="player in players" :key="player.id" :value="player.id" :disabled="player.id === player1 || player.id === champion?.id">{{ player.nickname }}</option>
        </select>
      </label>
    </div>
    <template v-if="mode === 'record'">
      <p class="small muted">Бой засчитается сразу, без подтверждения игроков: пояс перейдёт победителю. {{ pointsHint }}</p>
      <FightResultForm
        v-if="pair"
        :key="`${pair[0].id}-${pair[1].id}`"
        :player1="pair[0]"
        :player2="pair[1]"
        :busy="busy"
        submit-label="Записать и засчитать"
        @submit="record"
      />
      <p v-else class="small muted">Выберите {{ champion ? 'претендента' : 'обоих игроков' }} — появятся победитель, дата, способ и раунд.</p>
    </template>
    <form v-else class="stack" @submit.prevent="schedule">
      <label class="field">
        Дата и время (необязательно)
        <input v-model="scheduledAt" type="datetime-local" />
      </label>
      <p class="small muted">Итог потом вносят игроки, как обычно, или админ кнопкой «Внести итог» на странице пояса.</p>
      <button class="btn primary" type="submit" :disabled="busy || !pair">Назначить бой</button>
    </form>
  </div>
</template>
