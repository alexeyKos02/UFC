<script setup lang="ts">
import { reactive, ref } from 'vue'
import { api } from '../../api'
import StateBlock from '../../components/StateBlock.vue'
import { useAction, useLoad } from '../../feedback'
import { formatDateTime, fromLocalInput, promoTypeLabel, toLocalInput } from '../../format'
import type { PlayerBrief, Promo, PromoType, TournamentCard } from '../../types'

const list = useLoad(() => api.get<Promo[]>('/admin/promos'))
const tournaments = useLoad(() => api.get<TournamentCard[]>('/admin/tournaments'))
const players = useLoad(() => api.get<PlayerBrief[]>('/players/options'))
const { busy, run } = useAction()

interface PromoForm {
  type: PromoType
  title: string
  description: string
  tournament_id: number | ''
  fighter1_id: number | ''
  fighter2_id: number | ''
  fight_at: string
  player_id: number | ''
  show_from: string
  show_until: string
  sort_order: number
}

const blank = (): PromoForm => ({
  type: 'tournament',
  title: '',
  description: '',
  tournament_id: '',
  fighter1_id: '',
  fighter2_id: '',
  fight_at: '',
  player_id: '',
  show_from: '',
  show_until: '',
  sort_order: 0,
})

const form = reactive<PromoForm>(blank())
const editingId = ref<number | null>(null)

function reset(): void {
  editingId.value = null
  Object.assign(form, blank())
}

function edit(promo: Promo): void {
  editingId.value = promo.id
  Object.assign(form, {
    type: promo.type,
    title: promo.title,
    description: promo.description,
    tournament_id: promo.tournament?.id ?? '',
    fighter1_id: promo.fighter1?.id ?? '',
    fighter2_id: promo.fighter2?.id ?? '',
    fight_at: promo.fight_at ? toLocalInput(promo.fight_at) : '',
    player_id: promo.player?.id ?? '',
    show_from: promo.show_from ? toLocalInput(promo.show_from) : '',
    show_until: promo.show_until ? toLocalInput(promo.show_until) : '',
    sort_order: promo.sort_order,
  })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function optionalId(value: number | ''): number | null {
  return value === '' ? null : value
}

function optionalDate(value: string): string | null {
  return value ? fromLocalInput(value) : null
}

async function save(): Promise<void> {
  const body = {
    type: form.type,
    title: form.title,
    description: form.description,
    tournament_id: optionalId(form.tournament_id),
    fighter1_id: optionalId(form.fighter1_id),
    fighter2_id: optionalId(form.fighter2_id),
    fight_at: optionalDate(form.fight_at),
    player_id: optionalId(form.player_id),
    show_from: optionalDate(form.show_from),
    show_until: optionalDate(form.show_until),
    sort_order: form.sort_order,
  }
  const id = editingId.value
  const done = await run(
    () => (id ? api.patch(`/admin/promos/${id}`, body) : api.post('/admin/promos', body)),
    id ? 'Плашка обновлена' : 'Плашка создана, она скрыта до публикации',
  )
  if (done) {
    reset()
    await list.reload()
  }
}

async function setPublished(promo: Promo, published: boolean): Promise<void> {
  await run(() => api.post(`/admin/promos/${promo.id}/publish`, { published }), published ? 'Опубликовано' : 'Скрыто')
  await list.reload()
}

async function uploadImage(event: Event, promo: Promo): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await run(() => api.upload(`/admin/promos/${promo.id}/image`, file), 'Изображение загружено')
  input.value = ''
  await list.reload()
}

function subject(promo: Promo): string {
  if (promo.tournament) return promo.tournament.title
  if (promo.fighter1 && promo.fighter2) return `${promo.fighter1.nickname} — ${promo.fighter2.nickname}`
  return promo.player?.nickname ?? ''
}

function period(promo: Promo): string {
  if (!promo.show_from && !promo.show_until) return 'Без ограничений'
  return `${formatDateTime(promo.show_from)} — ${formatDateTime(promo.show_until)}`
}
</script>

<template>
  <section class="card stack">
    <h3>{{ editingId ? 'Редактировать плашку' : 'Новая плашка' }}</h3>
    <form class="stack" @submit.prevent="save">
      <div class="field-grid">
        <label class="field">
          Тип
          <select v-model="form.type">
            <option value="tournament">Турнир</option>
            <option value="fight_announcement">Анонс боя</option>
            <option value="fighter_of_week">Боец недели</option>
          </select>
        </label>
        <label class="field">Заголовок<input v-model="form.title" required maxlength="120" /></label>
        <label class="field">Порядок показа<input v-model.number="form.sort_order" type="number" required /></label>
      </div>
      <label class="field">Описание<textarea v-model="form.description" maxlength="2000"></textarea></label>

      <label v-if="form.type === 'tournament'" class="field">
        Турнир
        <select v-model.number="form.tournament_id" required>
          <option value="" disabled>Выберите турнир</option>
          <option v-for="item in tournaments.data.value" :key="item.id" :value="item.id">{{ item.title }}</option>
        </select>
      </label>

      <div v-if="form.type === 'fight_announcement'" class="field-grid">
        <label class="field">
          Первый участник
          <select v-model.number="form.fighter1_id" required>
            <option value="" disabled>Выберите игрока</option>
            <option v-for="player in players.data.value" :key="player.id" :value="player.id">{{ player.nickname }}</option>
          </select>
        </label>
        <label class="field">
          Второй участник
          <select v-model.number="form.fighter2_id" required>
            <option value="" disabled>Выберите игрока</option>
            <option v-for="player in players.data.value" :key="player.id" :value="player.id">{{ player.nickname }}</option>
          </select>
        </label>
        <label class="field">Дата и время (необязательно)<input v-model="form.fight_at" type="datetime-local" /></label>
      </div>

      <label v-if="form.type === 'fighter_of_week'" class="field">
        Боец
        <select v-model.number="form.player_id" required>
          <option value="" disabled>Выберите игрока</option>
          <option v-for="player in players.data.value" :key="player.id" :value="player.id">{{ player.nickname }}</option>
        </select>
      </label>

      <div class="field-grid">
        <label class="field">Показывать с<input v-model="form.show_from" type="datetime-local" :required="form.type === 'fighter_of_week'" /></label>
        <label class="field">Показывать до<input v-model="form.show_until" type="datetime-local" :required="form.type === 'fighter_of_week'" /></label>
      </div>
      <div class="row">
        <button class="btn primary" type="submit" :disabled="busy">{{ editingId ? 'Сохранить' : 'Создать' }}</button>
        <button v-if="editingId" class="btn" type="button" @click="reset">Отмена</button>
      </div>
    </form>
  </section>

  <StateBlock :loading="list.loading.value" :error="list.error.value" skeleton="list">
    <div v-if="list.data.value?.length" class="stack">
      <article v-for="promo in list.data.value" :key="promo.id" class="card stack">
        <div class="row between">
          <div class="stack" style="gap: 2px">
            <span class="kicker">{{ promoTypeLabel[promo.type] }} · порядок {{ promo.sort_order }}</span>
            <b>{{ promo.title }}</b>
            <span class="small muted">{{ subject(promo) }}</span>
          </div>
          <span class="badge" :class="promo.is_published ? 'tone-green' : 'tone-grey'">{{ promo.is_published ? 'Опубликована' : 'Скрыта' }}</span>
        </div>
        <p class="small muted">Период показа: {{ period(promo) }}</p>
        <div class="row">
          <button v-if="promo.is_published" class="btn sm" :disabled="busy" @click="setPublished(promo, false)">Скрыть</button>
          <button v-else class="btn sm primary" :disabled="busy" @click="setPublished(promo, true)">Опубликовать</button>
          <button class="btn sm" @click="edit(promo)">Изменить</button>
          <label v-if="promo.type === 'tournament'" class="field" style="flex: 1; min-width: 200px">
            <span class="sr-hidden">Изображение плашки</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="busy" aria-label="Изображение плашки" @change="uploadImage($event, promo)" />
          </label>
        </div>
      </article>
    </div>
    <p v-else class="empty">Плашек пока нет.</p>
  </StateBlock>
</template>
