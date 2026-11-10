<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../../api'
import Modal from '../../components/Modal.vue'
import PlayerChip from '../../components/PlayerChip.vue'
import StateBlock from '../../components/StateBlock.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { useAction, useLoad } from '../../feedback'
import { formatDateTime, fromLocalInput } from '../../format'
import type { Belt, PlayerBrief, TitleFight } from '../../types'

const list = useLoad(() => api.get<TitleFight[]>('/admin/title-fights'))
const belts = useLoad(() => api.get<Belt[]>('/belts'))
const players = useLoad(() => api.get<PlayerBrief[]>('/players/options'))
const { busy, run } = useAction()

const mainBelt = computed(() => belts.data.value?.find((belt) => belt.kind === 'main') ?? null)
const champion = computed(() => mainBelt.value?.champion ?? null)
const hasOpenFight = computed(() => list.data.value?.some((item) => item.status === 'scheduled') ?? false)

const player1 = ref<number | ''>('')
const player2 = ref<number | ''>('')
const scheduledAt = ref('')
const cancelling = ref<TitleFight | null>(null)
const reason = ref('')

async function schedule(): Promise<void> {
  const body = {
    player1_id: champion.value ? champion.value.id : player1.value,
    player2_id: player2.value,
    scheduled_at: scheduledAt.value ? fromLocalInput(scheduledAt.value) : null,
  }
  if (await run(() => api.post('/admin/title-fights', body), 'Бой назначен')) {
    player1.value = ''
    player2.value = ''
    scheduledAt.value = ''
    await list.reload()
  }
}

async function cancel(): Promise<void> {
  const item = cancelling.value
  if (!item) return
  if (await run(() => api.post(`/admin/title-fights/${item.id}/cancel`, { reason: reason.value }), 'Назначение отменено')) {
    cancelling.value = null
    reason.value = ''
    await list.reload()
  }
}
</script>

<template>
  <section class="card stack">
    <h3>Назначить бой за основной пояс</h3>
    <p v-if="hasOpenFight" class="small tone-amber">Незавершённый бой уже есть. Новый можно назначить после его завершения или отмены.</p>
    <p v-else-if="champion" class="small muted">Действующий чемпион: {{ champion.nickname }}. Выберите претендента.</p>
    <p v-else class="small muted">Пояс вакантен. Выберите двух активных игроков.</p>
    <form class="stack" @submit.prevent="schedule">
      <div class="field-grid">
        <label v-if="!champion" class="field">
          Первый игрок
          <select v-model.number="player1" required>
            <option value="" disabled>Выберите игрока</option>
            <option v-for="player in players.data.value" :key="player.id" :value="player.id" :disabled="player.id === player2">{{ player.nickname }}</option>
          </select>
        </label>
        <label class="field">
          {{ champion ? 'Претендент' : 'Второй игрок' }}
          <select v-model.number="player2" required>
            <option value="" disabled>Выберите игрока</option>
            <option v-for="player in players.data.value" :key="player.id" :value="player.id" :disabled="player.id === player1 || player.id === champion?.id">{{ player.nickname }}</option>
          </select>
        </label>
        <label class="field">
          Дата и время (необязательно)
          <input v-model="scheduledAt" type="datetime-local" />
        </label>
      </div>
      <button class="btn primary" type="submit" :disabled="busy || hasOpenFight" style="align-self: flex-start">Назначить бой</button>
    </form>
  </section>

  <StateBlock :loading="list.loading.value" :error="list.error.value">
    <div v-if="list.data.value?.length" class="stack">
      <article v-for="item in list.data.value" :key="item.id" class="card stack">
        <div class="row between">
          <span class="small muted">{{ item.scheduled_at ? formatDateTime(item.scheduled_at) : 'Дата не назначена' }}</span>
          <StatusBadge :title="item.status" />
        </div>
        <div class="fight-row">
          <PlayerChip :player="item.player1" />
          <span class="versus">VS</span>
          <div class="right"><PlayerChip :player="item.player2" /></div>
        </div>
        <p v-if="item.winner" class="small">Победитель: {{ item.winner.nickname }}{{ item.is_defense ? ' (защита пояса)' : '' }}</p>
        <p v-if="item.cancel_reason" class="small tone-grey">Причина отмены: {{ item.cancel_reason }}</p>
        <div class="row">
          <RouterLink v-if="item.fight" class="link small" :to="`/fights/${item.fight.id}`">Запись боя</RouterLink>
          <button v-if="item.status === 'scheduled'" class="btn sm danger" @click="cancelling = item">Отменить назначение</button>
        </div>
      </article>
    </div>
    <p v-else class="empty">Титульные бои ещё не назначались.</p>
  </StateBlock>

  <Modal v-if="cancelling" title="Отменить назначение" @close="cancelling = null">
    <p class="small muted">Карточка закроется для внесения и подтверждения результата.</p>
    <form class="stack" @submit.prevent="cancel">
      <label class="field">Причина<textarea v-model="reason" required minlength="3" maxlength="500"></textarea></label>
      <button class="btn danger" type="submit" :disabled="busy">Отменить назначение</button>
    </form>
  </Modal>
</template>
