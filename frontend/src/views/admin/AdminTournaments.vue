<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../../api'
import Modal from '../../components/Modal.vue'
import StateBlock from '../../components/StateBlock.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { useAction, useLoad } from '../../feedback'
import { seatsLine } from '../../format'
import type { Belt, TournamentCard } from '../../types'

const list = useLoad(() => api.get<TournamentCard[]>('/admin/tournaments'))
const belts = useLoad(() => api.get<Belt[]>('/belts'))
const { busy, run } = useAction()

const tournamentBelts = computed(() => (belts.data.value ?? []).filter((belt) => belt.kind === 'tournament'))
const emptyForm = { title: '', description: '', capacity: 8, win_points: 10, belt_id: 0 }
const form = reactive({ ...emptyForm })
const editingId = ref<number | null>(null)
const cancelling = ref<TournamentCard | null>(null)
const reason = ref('')

function edit(item: TournamentCard): void {
  editingId.value = item.id
  Object.assign(form, {
    title: item.title,
    description: item.description,
    capacity: item.capacity,
    win_points: item.win_points,
    belt_id: item.belt.id,
  })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function reset(): void {
  editingId.value = null
  Object.assign(form, emptyForm)
}

async function save(): Promise<void> {
  const body = { ...form }
  const id = editingId.value
  const done = await run(
    () => (id ? api.patch(`/admin/tournaments/${id}`, body) : api.post('/admin/tournaments', body)),
    id ? 'Турнир обновлён' : 'Турнир создан как черновик',
  )
  if (done) {
    reset()
    await list.reload()
  }
}

async function act(item: TournamentCard, action: 'publish' | 'start', message: string): Promise<void> {
  await run(() => api.post(`/admin/tournaments/${item.id}/${action}`), message)
  await list.reload()
}

async function cancel(): Promise<void> {
  const item = cancelling.value
  if (!item) return
  const done = await run(() => api.post(`/admin/tournaments/${item.id}/cancel`, { reason: reason.value }), 'Турнир отменён')
  if (done) {
    cancelling.value = null
    reason.value = ''
    await list.reload()
  }
}
</script>

<template>
  <section class="card stack">
    <h3>{{ editingId ? 'Редактировать турнир' : 'Новый турнир' }}</h3>
    <p v-if="!tournamentBelts.length && !belts.loading.value" class="small tone-amber">Сначала создайте турнирный пояс в разделе «Пояса».</p>
    <form class="stack" @submit.prevent="save">
      <div class="field-grid">
        <label class="field">Название<input v-model="form.title" required maxlength="120" /></label>
        <label class="field">Лимит участников<input v-model.number="form.capacity" type="number" min="2" max="128" required /></label>
        <label class="field">Очки за победу в турнире<input v-model.number="form.win_points" type="number" min="0" max="100000" step="1" required /></label>
        <label class="field">
          Турнирный пояс
          <select v-model.number="form.belt_id" required>
            <option :value="0" disabled>Выберите пояс</option>
            <option v-for="belt in tournamentBelts" :key="belt.id" :value="belt.id">{{ belt.name }}</option>
          </select>
        </label>
      </div>
      <label class="field">Описание<textarea v-model="form.description" maxlength="2000"></textarea></label>
      <div class="row">
        <button class="btn primary" type="submit" :disabled="busy || !form.belt_id">{{ editingId ? 'Сохранить' : 'Создать черновик' }}</button>
        <button v-if="editingId" class="btn" type="button" @click="reset">Отмена</button>
      </div>
    </form>
  </section>

  <StateBlock :loading="list.loading.value" :error="list.error.value" skeleton="table">
    <div v-if="list.data.value?.length" class="table-wrap">
      <table>
        <thead>
          <tr><th>Турнир</th><th>Статус</th><th class="hide-sm">Пояс</th><th class="num">Места</th><th class="num hide-sm">Очки</th><th>Действия</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in list.data.value" :key="item.id">
            <td><RouterLink class="link" :to="`/tournaments/${item.id}`">{{ item.title }}</RouterLink></td>
            <td><StatusBadge :tournament="item.status" /></td>
            <td class="hide-sm small">{{ item.belt.name }}</td>
            <td class="num small">{{ seatsLine(item) }}</td>
            <td class="num small hide-sm">+{{ item.win_points }}</td>
            <td>
              <div class="row" style="gap: 6px">
                <button v-if="item.status === 'draft'" class="btn sm primary" :disabled="busy" @click="act(item, 'publish', 'Регистрация открыта')">Открыть регистрацию</button>
                <button v-if="item.status === 'registration'" class="btn sm primary" :disabled="busy" @click="act(item, 'start', 'Турнир запущен, сетка создана')">Запустить</button>
                <button v-if="item.status !== 'cancelled'" class="btn sm" @click="edit(item)">Изменить</button>
                <button v-if="item.status === 'draft' || item.status === 'registration' || item.status === 'in_progress'" class="btn sm danger" @click="cancelling = item">Отменить</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="empty">Турниров пока нет.</p>
  </StateBlock>

  <Modal v-if="cancelling" :title="`Отменить «${cancelling.title}»`" @close="cancelling = null">
    <p class="small muted">Подтверждённые бои останутся в истории и статистике. Пояс выдан не будет, незавершённые записи закроются.</p>
    <form class="stack" @submit.prevent="cancel">
      <label class="field">Причина<textarea v-model="reason" required minlength="3" maxlength="500"></textarea></label>
      <button class="btn danger" type="submit" :disabled="busy">Отменить турнир</button>
    </form>
  </Modal>
</template>
