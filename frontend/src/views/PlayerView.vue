<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { setAccount } from '../auth'
import { BELT_MARK_LABELS, BELT_MARK_ORDER, beltMark } from '../beltMarks'
import BeltIcon from '../components/BeltIcon.vue'
import BeltMarkIcon from '../components/BeltMarkIcon.vue'
import ChampionMark from '../components/ChampionMark.vue'
import FightCard from '../components/FightCard.vue'
import HeadToHead from '../components/HeadToHead.vue'
import PlayerChip from '../components/PlayerChip.vue'
import RatingChart from '../components/RatingChart.vue'
import SkeletonBlock from '../components/SkeletonBlock.vue'
import StateBlock from '../components/StateBlock.vue'
import WinLossBar from '../components/WinLossBar.vue'
import { useAction, useLoad } from '../feedback'
import { formatDate, plural, tierLabel } from '../format'
import type { Account, FightBrief, PlayerProfile, RatingHistoryPoint } from '../types'

const HISTORY_PAGE = 10

const props = defineProps<{ id: string }>()
const { data, error, loading, reload } = useLoad(() => api.get<PlayerProfile>(`/players/${props.id}`))
const history = useLoad(() => api.get<FightBrief[]>(`/players/${props.id}/fights`))
const visibleFights = ref(HISTORY_PAGE)

const ratingHistory = useLoad(() => api.get<{ points: RatingHistoryPoint[] }>(`/players/${props.id}/rating-history`))
const chartMode = ref<'points' | 'place'>('points')
const chartPeriod = ref<'month' | 'all'>('all')
const MONTH_MS = 30 * 24 * 60 * 60 * 1000
const chartHistory = computed(() => {
  const all = ratingHistory.data.value?.points ?? []
  if (chartPeriod.value === 'all') return all
  const since = Date.now() - MONTH_MS
  return all.filter((item) => new Date(item.fought_at).getTime() >= since)
})
/** Легенда под графиком: только то, что на нём есть. */
const chartHasChampion = computed(() => chartHistory.value.some((item) => item.champion_after || item.champion_before))
const chartBeltMarks = computed(() => {
  const present = new Set(chartHistory.value.map(beltMark))
  return BELT_MARK_ORDER.filter((mark) => present.has(mark))
})

type ResultFilter = 'all' | 'wins' | 'losses'
const result = ref<ResultFilter>('all')
const playerId = computed(() => Number(props.id))
const filteredHistory = computed(() => {
  const fights = history.data.value ?? []
  if (result.value === 'all') return fights
  const wantWin = result.value === 'wins'
  return fights.filter((fight) => (fight.winner_id === playerId.value) === wantWin)
})
const resultOptions = computed(() => {
  const fights = history.data.value ?? []
  const wins = fights.filter((fight) => fight.winner_id === playerId.value).length
  return [
    { value: 'all' as const, label: 'Все', count: fights.length },
    { value: 'wins' as const, label: 'Победы', count: wins },
    { value: 'losses' as const, label: 'Поражения', count: fights.length - wins },
  ]
})

function setResult(value: ResultFilter): void {
  result.value = value
  visibleFights.value = HISTORY_PAGE
}
const { busy, run } = useAction()

const nickname = ref('')
watch(data, (value) => {
  if (value) nickname.value = value.player.nickname
})

function inactivityLine(info: NonNullable<PlayerProfile['rating']['inactivity']>): string {
  const days = `${info.days_without_fights} ${plural(info.days_without_fights, ['день', 'дня', 'дней'])}`
  if (info.lost_points > 0) {
    return `Без боёв ${days}: за простой снято ${info.lost_points} ${plural(info.lost_points, ['очко', 'очка', 'очков'])}. Каждую неделю снимается 3% от очков сверх 1000, пока не будет боя.`
  }
  return `Без боёв ${days}. С ${formatDate(info.decay_starts_at)} каждую неделю будет сниматься 3% от очков сверх 1000, пока не будет боя.`
}

async function saveNickname(): Promise<void> {
  const account = await run(() => api.patch<Account>('/me/profile', { nickname: nickname.value }), 'Ник обновлён')
  if (account) {
    setAccount(account)
    await reload()
  }
}

async function upload(event: Event, path: string): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const account = await run(() => api.upload<Account>(path, file), 'Изображение обновлено')
  input.value = ''
  if (account) {
    setAccount(account)
    await reload()
  }
}
</script>

<template>
  <main class="container page">
    <StateBlock :loading="loading" :error="error" skeleton="profile">
      <template v-if="data">
        <div class="profile-top">
          <div class="photo-wrap">
            <span v-if="data.rating.is_champion" class="photo-crown"><ChampionMark :size="26" /></span>
            <img v-if="data.player.full_body_url" class="full-body" :src="data.player.full_body_url" :alt="`${data.player.nickname} в полный рост`" />
            <svg v-else class="full-body" viewBox="0 0 120 200" role="img" aria-label="Фото в полный рост не загружено">
              <rect width="120" height="200" fill="#17191e" />
              <g fill="#3a3f4a">
                <circle cx="60" cy="34" r="16" />
                <path d="M38 56h44l8 62-11 3-5-38-3 42 3 62H63l-3-54-3 54H46l3-62-3-42-5 38-11-3z" />
              </g>
            </svg>
          </div>

          <div class="stack" style="gap: 16px">
            <div class="row">
              <h1>{{ data.player.nickname }}</h1>
              <span v-if="data.rating.tier" class="tier-tag" :class="`tier-${data.rating.tier}`">{{ tierLabel[data.rating.tier] }}</span>
              <span v-if="data.player.status === 'blocked'" class="badge tone-red">Заблокирован</span>
            </div>

            <div class="tiles">
              <div v-if="!data.rating.is_champion" class="tile">
                <b>{{ data.rating.display_place === null ? '—' : `№${data.rating.display_place}` }}</b>
                <span>Место<template v-if="data.rating.is_special"> · Спецместо</template></span>
              </div>
              <div class="tile"><b>{{ data.rating.points }}</b><span>Очки</span></div>
              <div class="tile"><b>{{ data.stats.best_streak }}</b><span>Лучшая серия</span></div>
            </div>

            <p v-if="data.rating.is_calibrating" class="small muted">
              Калибровка: меньше 5 боёв. В таблице игрок стоит ниже остальных, пока не сыграет пятый бой.
            </p>
            <p v-if="data.rating.inactivity" class="small tone-amber">
              {{ inactivityLine(data.rating.inactivity) }}
            </p>

            <WinLossBar :wins="data.stats.wins" :losses="data.stats.losses" :win-rate="data.stats.win_rate" />

            <HeadToHead v-if="data.head_to_head" :h2h="data.head_to_head" :rival="data.player" />

            <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr))">
              <div class="card stack">
                <h3>Хозяин</h3>
                <div v-for="item in data.stats.nemeses" :key="item.player.id" class="row between">
                  <PlayerChip :player="item.player" />
                  <span class="small muted">Поражений: {{ item.count }}</span>
                </div>
                <p v-if="!data.stats.nemeses.length" class="small muted">Поражений пока не было</p>
              </div>
              <div class="card stack">
                <h3>Владеет</h3>
                <div v-for="item in data.stats.victims" :key="item.player.id" class="row between">
                  <PlayerChip :player="item.player" />
                  <span class="small muted">Побед: {{ item.count }}</span>
                </div>
                <p v-if="!data.stats.victims.length" class="small muted">Побед пока не было</p>
              </div>
            </div>
          </div>
        </div>

        <section v-if="data.is_me" class="card stack">
          <h3>Редактировать профиль</h3>
          <div class="field-grid">
            <form class="field" @submit.prevent="saveNickname">
              Ник
              <div class="row" style="flex-wrap: nowrap">
                <input v-model="nickname" required minlength="2" maxlength="32" />
                <button class="btn" type="submit" :disabled="busy">Сохранить</button>
              </div>
            </form>
            <label class="field">
              Аватар (JPEG, PNG или WEBP, до 5 МБ)
              <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="busy" @change="upload($event, '/me/avatar')" />
            </label>
            <label class="field">
              Фото в полный рост (JPEG, PNG или WEBP, до 5 МБ)
              <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="busy" @change="upload($event, '/me/full-body')" />
            </label>
          </div>
        </section>

        <section v-if="data.belts.active.length" class="section">
          <h2>Активные пояса</h2>
          <div class="grid">
            <div v-for="item in data.belts.active" :key="item.belt.id" class="card belt-row">
              <BeltIcon :belt="item.belt" :size="56" />
              <div class="stack" style="gap: 4px; min-width: 0">
                <span class="badge tone-gold">{{ item.caption }}</span>
                <RouterLink class="link" :to="`/belts/${item.belt.id}`">{{ item.belt.name }}</RouterLink>
                <ul class="small muted" style="margin: 0; padding-left: 16px">
                  <li v-for="win in item.wins" :key="win.id">
                    {{ formatDate(win.won_at) }}{{ win.is_defense ? ', защита' : '' }}
                    <template v-if="win.tournament">— <RouterLink class="link" :to="`/tournaments/${win.tournament.id}`">{{ win.tournament.title }}</RouterLink></template>
                    <template v-else-if="win.fight_id">— <RouterLink class="link" :to="`/fights/${win.fight_id}`">титульный бой</RouterLink></template>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section v-if="data.belts.past.length" class="section">
          <h2>Прошлые пояса</h2>
          <div class="grid">
            <div v-for="item in data.belts.past" :key="item.belt.id" class="card belt-row">
              <BeltIcon :belt="item.belt" past :size="56" />
              <div class="stack" style="gap: 4px; min-width: 0">
                <span class="badge plain tone-grey" style="white-space: normal">{{ item.caption }}</span>
                <ul class="small muted" style="margin: 0; padding-left: 16px">
                  <li v-for="win in item.wins" :key="win.id">
                    {{ formatDate(win.won_at) }}{{ win.is_defense ? ', защита' : '' }}
                    <template v-if="win.tournament">— <RouterLink class="link" :to="`/tournaments/${win.tournament.id}`">{{ win.tournament.title }}</RouterLink></template>
                    <template v-else-if="win.fight_id">— <RouterLink class="link" :to="`/fights/${win.fight_id}`">титульный бой</RouterLink></template>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section v-if="ratingHistory.data.value?.points.length" class="section">
          <h2>Динамика</h2>
          <div class="card stack">
            <div class="chart-controls">
              <div class="filter-chips" role="group" aria-label="Что показать">
                <button type="button" :aria-pressed="chartMode === 'points'" @click="chartMode = 'points'">Очки</button>
                <button type="button" :aria-pressed="chartMode === 'place'" @click="chartMode = 'place'">Место</button>
              </div>
              <div class="filter-chips" role="group" aria-label="Период">
                <button type="button" :aria-pressed="chartPeriod === 'month'" @click="chartPeriod = 'month'">30 дней</button>
                <button type="button" :aria-pressed="chartPeriod === 'all'" @click="chartPeriod = 'all'">Всё время</button>
              </div>
            </div>
            <RatingChart v-if="chartHistory.length" :history="chartHistory" :mode="chartMode" />
            <p v-else class="small muted">За последние 30 дней боёв не было.</p>
            <div v-if="chartHasChampion || chartBeltMarks.length" class="chart-legend small muted">
              <span v-if="chartHasChampion" class="chart-legend-item">
                <span class="chart-legend-champion" aria-hidden="true"></span>с поясом чемпиона
              </span>
              <span v-for="mark in chartBeltMarks" :key="mark" class="chart-legend-item">
                <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><BeltMarkIcon :mark="mark" /></svg>
                {{ BELT_MARK_LABELS[mark] }}
              </span>
            </div>
            <p class="small muted">
              {{ chartMode === 'points' ? 'Очки после каждого боя.' : 'Место в таблице рейтинга после каждого боя.' }}
              Масштаб: «+ / −», Ctrl + колесо или двумя пальцами.
            </p>
          </div>
        </section>

        <section class="section">
          <div class="section-head">
            <h2>История боёв</h2>
            <div v-if="history.data.value?.length" class="filter-chips" role="group" aria-label="Результат боя">
              <button
                v-for="option in resultOptions"
                :key="option.value"
                type="button"
                :aria-pressed="result === option.value"
                @click="setResult(option.value)"
              >
                {{ option.label }} <b>{{ option.count }}</b>
              </button>
            </div>
          </div>
          <div v-if="filteredHistory.length" class="stack" style="gap: 16px">
            <FightCard v-for="fight in filteredHistory.slice(0, visibleFights)" :key="fight.id" :fight="fight" />
          </div>
          <SkeletonBlock v-else-if="history.loading.value" kind="list" :count="2" />
          <p v-else-if="history.data.value?.length" class="empty">{{ result === 'wins' ? 'Побед пока нет.' : 'Поражений пока нет.' }}</p>
          <p v-else class="empty">Подтверждённых боёв пока нет.</p>
          <button
            v-if="filteredHistory.length > visibleFights"
            class="btn"
            style="align-self: center"
            @click="visibleFights += HISTORY_PAGE"
          >
            Показать ещё
          </button>
        </section>
      </template>
    </StateBlock>
  </main>
</template>
