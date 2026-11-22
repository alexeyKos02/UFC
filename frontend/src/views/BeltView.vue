<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { isStaff } from '../auth'
import BeltIcon from '../components/BeltIcon.vue'
import FightResultForm from '../components/FightResultForm.vue'
import Modal from '../components/Modal.vue'
import PlayerChip from '../components/PlayerChip.vue'
import StateBlock from '../components/StateBlock.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useAction, useLoad } from '../feedback'
import { formatDate, formatDateTime, fromLocalInput } from '../format'
import type { BeltDetail, PlayerBrief, ResultPayload } from '../types'

const props = defineProps<{ id: string }>()
const { data, error, loading, reload } = useLoad(() => api.get<BeltDetail>(`/belts/${props.id}`))
// Список игроков нужен только админу и владельцу — для назначения боя за пояс.
const players = isStaff.value ? useLoad(() => api.get<PlayerBrief[]>('/players/options')) : null
const { busy, run } = useAction()

const openFight = computed(() => data.value?.open_title_fight ?? null)
const champion = computed(() => data.value?.champion ?? null)
// Результат, который игроки внесли сами и ещё не подтвердили: итог админа его заменит.
const playerRecord = computed(() => {
  const fight = openFight.value?.fight
  return fight && fight.status !== 'confirmed' ? fight : null
})

const player1 = ref<number | ''>('')
const player2 = ref<number | ''>('')
const scheduledAt = ref('')

async function schedule(): Promise<void> {
  if (!data.value) return
  const body = {
    belt_id: data.value.id,
    player1_id: champion.value ? champion.value.id : player1.value,
    player2_id: player2.value,
    scheduled_at: scheduledAt.value ? fromLocalInput(scheduledAt.value) : null,
  }
  if (await run(() => api.post('/admin/title-fights', body), 'Бой за пояс назначен')) {
    player1.value = ''
    player2.value = ''
    scheduledAt.value = ''
    await reload()
  }
}

const recording = ref(false)

async function recordResult(payload: ResultPayload): Promise<void> {
  const fight = openFight.value
  if (!fight) return
  if (await run(() => api.post(`/admin/title-fights/${fight.id}/result`, payload), 'Итог засчитан')) {
    recording.value = false
    await reload()
  }
}

const cancelling = ref(false)
const cancelReason = ref('')

async function cancelFight(): Promise<void> {
  const fight = openFight.value
  if (!fight) return
  if (await run(() => api.post(`/admin/title-fights/${fight.id}/cancel`, { reason: cancelReason.value }), 'Бой отменён')) {
    cancelling.value = false
    cancelReason.value = ''
    await reload()
  }
}
</script>

<template>
  <main class="container page">
    <StateBlock :loading="loading" :error="error" skeleton="table">
      <template v-if="data">
        <div class="belt-row">
          <BeltIcon :belt="data" :size="72" />
          <div class="stack" style="gap: 4px">
            <h1>{{ data.name }}</h1>
            <span class="muted">{{ data.kind === 'main' ? 'Основной пояс' : 'Турнирный пояс' }}</span>
          </div>
        </div>
        <section class="section">
          <h2>Действующий чемпион</h2>
          <div v-if="data.champion" class="winner-banner">
            <BeltIcon :belt="data" :size="52" />
            <div class="stack" style="gap: 4px">
              <span class="kicker" style="color: var(--gold)">Действующий чемпион</span>
              <PlayerChip :player="data.champion" :size="32" />
            </div>
          </div>
          <p v-else class="empty">Пояс вакантен.</p>
        </section>

        <section v-if="openFight || isStaff" class="section">
          <h2>Бой за пояс</h2>
          <article v-if="openFight" class="card stack">
            <div class="row between">
              <span class="small muted">{{ openFight.scheduled_at ? formatDateTime(openFight.scheduled_at) : 'Дата не назначена' }}</span>
              <StatusBadge :title="openFight.status" />
            </div>
            <div class="fight-row">
              <PlayerChip :player="openFight.player1" />
              <span class="versus">VS</span>
              <div class="right"><PlayerChip :player="openFight.player2" /></div>
            </div>
            <p v-if="playerRecord" class="small muted">
              Игроки внесли результат, он ждёт подтверждения:
              <RouterLink class="link" :to="`/fights/${playerRecord.id}`">запись боя</RouterLink>.
              <template v-if="isStaff"> Итог, внесённый здесь, заменит его.</template>
            </p>
            <div v-if="isStaff" class="row">
              <button class="btn primary" type="button" :disabled="busy" @click="recording = true">Внести итог</button>
              <button class="btn danger" type="button" :disabled="busy" @click="cancelling = true">Отменить бой</button>
            </div>
          </article>
          <form v-else-if="isStaff" class="card stack" @submit.prevent="schedule">
            <p v-if="champion" class="small muted">Чемпион {{ champion.nickname }} защищает пояс. Выберите претендента.</p>
            <p v-else class="small muted">Пояс вакантен: выберите двух игроков.</p>
            <div class="field-grid">
              <label v-if="!champion" class="field">
                Первый игрок
                <select v-model.number="player1" required>
                  <option value="" disabled>Выберите игрока</option>
                  <option v-for="player in players?.data.value" :key="player.id" :value="player.id" :disabled="player.id === player2">{{ player.nickname }}</option>
                </select>
              </label>
              <label class="field">
                {{ champion ? 'Претендент' : 'Второй игрок' }}
                <select v-model.number="player2" required>
                  <option value="" disabled>Выберите игрока</option>
                  <option v-for="player in players?.data.value" :key="player.id" :value="player.id" :disabled="player.id === player1 || player.id === champion?.id">{{ player.nickname }}</option>
                </select>
              </label>
              <label class="field">
                Дата и время (необязательно)
                <input v-model="scheduledAt" type="datetime-local" />
              </label>
            </div>
            <p class="small muted">Итог потом вносят игроки, как обычно, или админ здесь — тогда бой засчитывается сразу. Бой за пояс — бой лиги: очки начисляются по Elo.</p>
            <button class="btn primary" type="submit" :disabled="busy" style="align-self: flex-start">Назначить бой</button>
          </form>
        </section>

        <section class="section">
          <h2>История победителей</h2>
          <div v-if="data.history.length" class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Победитель</th>
                  <th>Где выигран</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="win in data.history" :key="win.id">
                  <td class="small">{{ formatDate(win.won_at) }}</td>
                  <td>
                    <div class="row" style="gap: 6px">
                      <PlayerChip :player="win.player" :size="24" />
                      <span v-if="win.is_defense" class="badge plain tone-gold">Защита</span>
                    </div>
                  </td>
                  <td class="small">
                    <RouterLink v-if="win.tournament" class="link" :to="`/tournaments/${win.tournament.id}`">{{ win.tournament.title }}</RouterLink>
                    <RouterLink v-else-if="win.fight_id" class="link" :to="`/fights/${win.fight_id}`">Титульный бой #{{ win.fight_id }}</RouterLink>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="empty">Этот пояс ещё никто не выигрывал.</p>
        </section>
      </template>
    </StateBlock>

    <Modal v-if="recording && openFight" :title="`Итог боя за пояс «${data?.name}»`" @close="recording = false">
      <p class="small muted">Бой засчитается сразу, без подтверждения игроков: пояс перейдёт победителю, очки начислятся.</p>
      <FightResultForm :player1="openFight.player1" :player2="openFight.player2" :busy="busy" submit-label="Засчитать итог" @submit="recordResult" />
    </Modal>

    <Modal v-if="cancelling && openFight" title="Отменить бой за пояс" @close="cancelling = false">
      <p class="small muted">Назначение закроется: внести и подтвердить результат будет нельзя.</p>
      <form class="stack" @submit.prevent="cancelFight">
        <label class="field">Причина<textarea v-model="cancelReason" required minlength="3" maxlength="500"></textarea></label>
        <button class="btn danger" type="submit" :disabled="busy">Отменить бой</button>
      </form>
    </Modal>
  </main>
</template>
