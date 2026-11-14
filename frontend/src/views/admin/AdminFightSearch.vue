<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../../api'
import Modal from '../../components/Modal.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { useAction } from '../../feedback'
import { boutCaption, formatBoutDate, formatDateTime, methodLabel } from '../../format'
import type { FightBrief, FightSearchPage } from '../../types'

/**
 * Поиск подтверждённых боёв по участникам и дате и удаление боя с откатом очков,
 * пояса и сетки турнира. Удалённые бои остаются в базе и находятся фильтром «Удалённые».
 */
type SearchState = 'confirmed' | 'deleted' | 'all'

const filters = reactive({ player: '', opponent: '', from: '', to: '', state: 'confirmed' as SearchState })
const items = ref<FightBrief[]>([])
const total = ref(0)
const loaded = ref(false)
const { busy, run } = useAction()
const deleting = ref<FightBrief | null>(null)
const reason = ref('')

/** Дата из поля — начало этого дня в часовом поясе браузера. */
function dayStart(value: string, plusDays = 0): string {
  const day = new Date(`${value}T00:00:00`)
  day.setDate(day.getDate() + plusDays)
  return day.toISOString()
}

function query(offset: number): string {
  const params = new URLSearchParams({ state: filters.state, offset: String(offset) })
  if (filters.player.trim()) params.set('player', filters.player.trim())
  if (filters.opponent.trim()) params.set('opponent', filters.opponent.trim())
  if (filters.from) params.set('date_from', dayStart(filters.from))
  // «По» включает весь выбранный день.
  if (filters.to) params.set('date_to', dayStart(filters.to, 1))
  return `/admin/fights/search?${params}`
}

async function search(): Promise<void> {
  const page = await run(() => api.get<FightSearchPage>(query(0)))
  if (!page) return
  items.value = page.items
  total.value = page.total
  loaded.value = true
}

async function more(): Promise<void> {
  const page = await run(() => api.get<FightSearchPage>(query(items.value.length)))
  if (!page) return
  items.value = [...items.value, ...page.items]
  total.value = page.total
}

function reset(): void {
  Object.assign(filters, { player: '', opponent: '', from: '', to: '', state: 'confirmed' })
  search()
}

onMounted(search)

function winnerName(row: FightBrief): string {
  return row.winner_id === row.player1.id ? row.player1.nickname : row.player2.nickname
}

const consequences = computed(() => {
  const row = deleting.value
  if (!row) return []
  const list = ['Очки за бой снимутся у обоих, история пересчитается с даты боя — у следующих боёв очки могут измениться.']
  if (row.kind === 'title') {
    list.push('Пояс вернётся тому, у кого он был до боя, а титульный бой снова будет ждать результата.')
  }
  if (row.kind === 'tournament') {
    list.push(
      'Матч турнира снова будет ждать результата, победитель уйдёт из следующего круга. Если это финал — турнир снова пойдёт, пояс и приз снимутся.',
    )
  }
  if (row.kind !== 'regular') {
    list.push('Если после этого боя пояс уже переходил или победитель сыграл следующий круг, удаление не пройдёт: сначала удалите более поздний бой.')
  }
  return list
})

function close(): void {
  deleting.value = null
  reason.value = ''
}

async function remove(): Promise<void> {
  const row = deleting.value
  if (!row) return
  if (await run(() => api.post(`/admin/fights/${row.id}/delete`, { reason: reason.value }), 'Бой удалён, очки пересчитаны')) {
    close()
    await search()
  }
}
</script>

<template>
  <section class="section">
    <h2>Поиск боёв</h2>
    <p class="small muted">
      Подтверждённые бои по нику участника и дате боя, свежие сверху. С двумя никами — бои именно этой пары.
      Удалённый бой остаётся в истории админки, очки и пояса откатываются.
    </p>
    <form class="card field-grid" @submit.prevent="search">
      <label class="field">
        Игрок
        <input v-model="filters.player" maxlength="32" placeholder="Часть ника" autocomplete="off" />
      </label>
      <label class="field">
        Соперник
        <input v-model="filters.opponent" maxlength="32" placeholder="Часть ника" autocomplete="off" />
      </label>
      <label class="field">
        С
        <input v-model="filters.from" type="date" />
      </label>
      <label class="field">
        По
        <input v-model="filters.to" type="date" />
      </label>
      <label class="field">
        Показать
        <select v-model="filters.state">
          <option value="confirmed">Подтверждённые</option>
          <option value="deleted">Удалённые</option>
          <option value="all">Все</option>
        </select>
      </label>
      <div class="row fight-search-actions">
        <button class="btn primary" type="submit" :disabled="busy">Найти</button>
        <button class="btn" type="button" :disabled="busy" @click="reset">Сбросить</button>
      </div>
    </form>

    <template v-if="loaded">
      <p class="small muted">Найдено: {{ total }}</p>
      <div v-if="items.length" class="stack" style="gap: 12px">
        <article v-for="row in items" :key="row.id" class="card stack open-fight">
          <div class="row between">
            <RouterLink class="link" :to="`/fights/${row.id}`">
              <b>{{ row.player1.nickname }} — {{ row.player2.nickname }}</b>
            </RouterLink>
            <StatusBadge :fight="row.status" />
          </div>
          <p class="small">
            Бой #{{ row.id }} от {{ formatBoutDate(row.fought_at) }} · {{ boutCaption[row.kind].toLowerCase() }} · победа
            {{ winnerName(row) }}<template v-if="row.method">, {{ methodLabel[row.method] }}</template>.
          </p>
          <p v-if="row.deletion" class="small tone-red">
            Удалён {{ formatDateTime(row.deletion.at) }}<template v-if="row.deletion.by">, {{ row.deletion.by.nickname }}</template><template v-if="row.deletion.reason">: {{ row.deletion.reason }}</template>
          </p>
          <div v-if="row.status === 'confirmed'" class="row">
            <button class="btn sm danger" :disabled="busy" @click="deleting = row">Удалить</button>
          </div>
        </article>
        <button v-if="items.length < total" class="btn" type="button" :disabled="busy" @click="more">
          Показать ещё ({{ total - items.length }})
        </button>
      </div>
      <p v-else class="empty">Ничего не нашлось.</p>
    </template>
  </section>

  <Modal v-if="deleting" title="Удалить бой" @close="close">
    <form class="stack" @submit.prevent="remove">
      <p class="small">
        {{ deleting.player1.nickname }} — {{ deleting.player2.nickname }}, {{ formatBoutDate(deleting.fought_at) }},
        {{ boutCaption[deleting.kind].toLowerCase() }}. Победа {{ winnerName(deleting) }}.
      </p>
      <ul class="small stack" style="gap: 6px; padding-left: 18px">
        <li v-for="line in consequences" :key="line">{{ line }}</li>
      </ul>
      <label class="field">
        Причина
        <textarea v-model="reason" required minlength="3" maxlength="500" placeholder="Например: бой записан по ошибке"></textarea>
      </label>
      <button class="btn danger" type="submit" :disabled="busy">Удалить бой</button>
    </form>
  </Modal>
</template>
