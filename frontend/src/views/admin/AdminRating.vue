<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../../api'
import ChampionMark from '../../components/ChampionMark.vue'
import Modal from '../../components/Modal.vue'
import PlayerChip from '../../components/PlayerChip.vue'
import StateBlock from '../../components/StateBlock.vue'
import { useAction, useLoad } from '../../feedback'
import { formatDateTime, signed } from '../../format'
import type { AdjustmentLogRow, AdminRating, SpecialPlaceLogRow, UpsetRow } from '../../types'

const rating = useLoad(() => api.get<AdminRating>('/admin/rating'))
const upsets = useLoad(() => api.get<UpsetRow[]>('/admin/rating/upsets'))
const adjustmentLog = useLoad(() => api.get<AdjustmentLogRow[]>('/admin/rating/adjustment-log'))
const placeLog = useLoad(() => api.get<SpecialPlaceLogRow[]>('/admin/rating/special-place-log'))
const { busy, run } = useAction()

const places = reactive<Record<number, number | ''>>({})
watch(rating.data, (value) => {
  if (!value) return
  const pinned = new Map(value.special_places.map((item) => [item.player.id, item.place]))
  for (const row of value.rows) places[row.player.id] = pinned.get(row.player.id) ?? ''
})

const pinnedIds = computed(() => new Set(rating.data.value?.special_places.map((item) => item.player.id)))

const blockedHolders = computed(() => {
  if (!rating.data.value) return []
  const active = new Set(rating.data.value.rows.map((row) => row.player.id))
  return rating.data.value.special_places.filter((item) => !active.has(item.player.id))
})

async function refreshAll(): Promise<void> {
  await Promise.all([rating.reload(), upsets.reload(), adjustmentLog.reload(), placeLog.reload()])
}

async function setPlace(playerId: number): Promise<void> {
  await run(() => api.put(`/admin/rating/special-places/${playerId}`, { place: places[playerId] }), 'Спецместо сохранено')
  await refreshAll()
}

async function clearPlace(playerId: number): Promise<void> {
  await run(() => api.delete(`/admin/rating/special-places/${playerId}`), 'Спецместо снято')
  await refreshAll()
}

const editing = ref<UpsetRow | null>(null)
const form = reactive({ playerId: 0, points: 1, reason: '' })
const cancelling = ref<UpsetRow | null>(null)
const cancelReason = ref('')

function openEditor(row: UpsetRow): void {
  editing.value = row
  const current = row.adjustment?.status === 'active' ? row.adjustment.winner_delta : 0
  form.playerId = row.winner.id
  form.points = current || 1
  form.reason = row.adjustment?.status === 'active' ? (row.adjustment.reason ?? '') : ''
}

const preview = computed(() => {
  const row = editing.value
  if (!row) return null
  const manualWinner = form.playerId === row.winner.id ? form.points : -form.points
  return {
    manualWinner,
    manualLoser: -manualWinner,
    totalWinner: row.auto_delta + manualWinner,
    totalLoser: -row.auto_delta - manualWinner,
  }
})

async function saveAdjustment(): Promise<void> {
  const row = editing.value
  if (!row) return
  const body = {
    player_id: form.playerId,
    points: form.points,
    reason: form.reason,
    expected_version: row.adjustment?.version ?? 0,
  }
  if (await run(() => api.put(`/admin/rating/adjustments/${row.fight_id}`, body), 'Корректировка сохранена')) {
    editing.value = null
    await refreshAll()
  }
}

async function cancelAdjustment(): Promise<void> {
  const row = cancelling.value
  if (!row?.adjustment) return
  const body = { reason: cancelReason.value, expected_version: row.adjustment.version }
  if (await run(() => api.post(`/admin/rating/adjustments/${row.fight_id}/cancel`, body), 'Корректировка отменена')) {
    cancelling.value = null
    cancelReason.value = ''
    await refreshAll()
  }
}

const actionLabel = { create: 'Создана', update: 'Изменена', cancel: 'Отменена' }
const placeActionLabel = { set: 'Назначено', change: 'Изменено', clear: 'Снято' }
</script>

<template>
  <section class="section">
    <h2>Спецместа</h2>
    <StateBlock :loading="rating.loading.value" :error="rating.error.value">
      <p class="small muted">Спецместо влияет только на отображение. Очки за бой считаются по Elo из очков обоих игроков, апсеты — по месту по очкам. Чемпион основного пояса стоит над таблицей без номера, его спецместо начнёт действовать после потери пояса. Активных игроков: {{ rating.data.value?.active_count }}.</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th class="num">В таблице</th><th class="num">По очкам</th><th>Игрок</th><th class="num">Очки</th><th>Спецместо</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in rating.data.value?.rows" :key="row.player.id">
              <td class="num">
                <ChampionMark v-if="row.is_champion" />
                <span v-else class="place">№{{ row.display_place }}</span>
              </td>
              <td class="num">№{{ row.points_place }}</td>
              <td>
                <div class="row" style="gap: 6px">
                  <PlayerChip :player="row.player" :size="24" />
                  <span v-if="row.is_special" class="badge plain tone-gold">Спецместо</span>
                </div>
              </td>
              <td class="num">{{ row.points }}</td>
              <td>
                <form class="row" style="gap: 6px; flex-wrap: nowrap" @submit.prevent="setPlace(row.player.id)">
                  <input v-model.number="places[row.player.id]" class="inline-input" type="number" min="1" :max="rating.data.value?.active_count" required :aria-label="`Спецместо игрока ${row.player.nickname}`" />
                  <button class="btn sm" type="submit" :disabled="busy">{{ pinnedIds.has(row.player.id) ? 'Изменить' : 'Закрепить' }}</button>
                  <button v-if="pinnedIds.has(row.player.id)" class="btn sm danger" type="button" :disabled="busy" @click="clearPlace(row.player.id)">Снять</button>
                </form>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="blockedHolders.length" class="card stack">
        <h3>Спецместа заблокированных игроков</h3>
        <div v-for="item in blockedHolders" :key="item.player.id" class="row between">
          <span>№{{ item.place }} — {{ item.player.nickname }}</span>
          <button class="btn sm danger" :disabled="busy" @click="clearPlace(item.player.id)">Снять</button>
        </div>
      </div>
    </StateBlock>
  </section>

  <section class="section">
    <h2>Ручная корректировка за апсет</h2>
    <p class="small muted">В списке только подтверждённые бои, где победитель был ниже соперника на 3 места или больше.</p>
    <StateBlock :loading="upsets.loading.value" :error="upsets.error.value">
      <div v-if="upsets.data.value?.length" class="table-wrap">
        <table>
          <thead>
            <tr><th>Бой</th><th>Победитель</th><th>Проигравший</th><th class="num">Авто</th><th class="num">Вручную</th><th>Действия</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in upsets.data.value" :key="row.fight_id">
              <td class="small"><RouterLink class="link" :to="`/fights/${row.fight_id}`">#{{ row.fight_id }}</RouterLink><br />{{ formatDateTime(row.fought_at) }}</td>
              <td><PlayerChip :player="row.winner" :size="24" /><br /><span class="small muted">было №{{ row.winner_place_before }}</span></td>
              <td><PlayerChip :player="row.loser" :size="24" /><br /><span class="small muted">было №{{ row.loser_place_before }}</span></td>
              <td class="num">{{ signed(row.auto_delta) }}</td>
              <td class="num">
                <template v-if="row.adjustment?.status === 'active'">{{ signed(row.adjustment.winner_delta) }}</template>
                <template v-else>—</template>
              </td>
              <td>
                <div class="row" style="gap: 6px">
                  <button class="btn sm" @click="openEditor(row)">{{ row.adjustment?.status === 'active' ? 'Изменить' : 'Добавить' }}</button>
                  <button v-if="row.adjustment?.status === 'active'" class="btn sm danger" @click="cancelling = row">Отменить</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="empty">Подходящих боёв нет.</p>
    </StateBlock>
  </section>

  <section class="section">
    <h2>Журнал корректировок</h2>
    <div v-if="adjustmentLog.data.value?.length" class="table-wrap">
      <table>
        <thead>
          <tr><th>Время</th><th>Автор</th><th>Действие</th><th>Бой</th><th>Причина</th><th class="num">Корректировка</th><th class="num">Очки</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in adjustmentLog.data.value" :key="row.id" class="small">
            <td>{{ formatDateTime(row.created_at) }}</td>
            <td>{{ row.actor.nickname }}</td>
            <td>{{ actionLabel[row.action] }}</td>
            <td><RouterLink class="link" :to="`/fights/${row.fight_id}`">#{{ row.fight_id }}</RouterLink></td>
            <td>{{ row.reason }}</td>
            <td class="num">{{ signed(row.winner_delta_before) }} → {{ signed(row.winner_delta_after) }}</td>
            <td class="num">
              {{ row.winner.nickname }}: {{ row.winner_points_before }} → {{ row.winner_points_after }}<br />
              {{ row.loser.nickname }}: {{ row.loser_points_before }} → {{ row.loser_points_after }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="empty">Записей нет.</p>
  </section>

  <section class="section">
    <h2>Журнал спецмест</h2>
    <div v-if="placeLog.data.value?.length" class="table-wrap">
      <table>
        <thead><tr><th>Время</th><th>Автор</th><th>Игрок</th><th>Действие</th><th class="num">Номер</th></tr></thead>
        <tbody>
          <tr v-for="row in placeLog.data.value" :key="row.id" class="small">
            <td>{{ formatDateTime(row.created_at) }}</td>
            <td>{{ row.actor.nickname }}</td>
            <td>{{ row.player.nickname }}</td>
            <td>{{ placeActionLabel[row.action] }}</td>
            <td class="num">{{ row.place_before ?? '—' }} → {{ row.place_after ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="empty">Записей нет.</p>
  </section>

  <Modal v-if="editing" title="Корректировка очков" @close="editing = null">
    <form class="stack" @submit.prevent="saveAdjustment">
      <fieldset class="stack" style="border: 0; padding: 0; margin: 0">
        <legend class="small muted" style="padding: 0; margin-bottom: 6px">Участник</legend>
        <div class="choice-group">
          <label class="choice"><input v-model="form.playerId" type="radio" :value="editing.winner.id" /> {{ editing.winner.nickname }}</label>
          <label class="choice"><input v-model="form.playerId" type="radio" :value="editing.loser.id" /> {{ editing.loser.nickname }}</label>
        </div>
      </fieldset>
      <label class="field">
        Очки (со знаком минус, чтобы снять)
        <input v-model.number="form.points" type="number" step="1" required />
      </label>
      <label class="field">Причина<textarea v-model="form.reason" required minlength="3" maxlength="500"></textarea></label>
      <div v-if="preview && form.points" class="preview">
        <p>{{ editing.winner.nickname }}: автоматически {{ signed(editing.auto_delta) }}, вручную {{ signed(preview.manualWinner) }}, итог по бою <b>{{ signed(preview.totalWinner) }}</b></p>
        <p>{{ editing.loser.nickname }}: автоматически {{ signed(-editing.auto_delta) }}, вручную {{ signed(preview.manualLoser) }}, итог по бою <b>{{ signed(preview.totalLoser) }}</b></p>
      </div>
      <button class="btn primary" type="submit" :disabled="busy || !form.points">Сохранить</button>
    </form>
  </Modal>

  <Modal v-if="cancelling" title="Отменить корректировку" @close="cancelling = null">
    <p class="small muted">Вручную перенесённые очки вернутся. Автоматические начисления не изменятся.</p>
    <form class="stack" @submit.prevent="cancelAdjustment">
      <label class="field">Причина<textarea v-model="cancelReason" required minlength="3" maxlength="500"></textarea></label>
      <button class="btn danger" type="submit" :disabled="busy">Отменить корректировку</button>
    </form>
  </Modal>
</template>
