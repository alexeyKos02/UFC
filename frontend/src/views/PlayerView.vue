<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { setAccount } from '../auth'
import BeltIcon from '../components/BeltIcon.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'
import PlayerChip from '../components/PlayerChip.vue'
import StateBlock from '../components/StateBlock.vue'
import { useAction, useLoad } from '../feedback'
import { fightKindLabel, formatDate, formatDateTime, resultLine, signed } from '../format'
import type { Account, HistoryItem, PlayerProfile } from '../types'

const props = defineProps<{ id: string }>()
const { data, error, loading, reload } = useLoad(() => api.get<PlayerProfile>(`/players/${props.id}`))
const history = useLoad(() => api.get<HistoryItem[]>(`/players/${props.id}/fights`))
const { busy, run } = useAction()

const nickname = ref('')
watch(data, (value) => {
  if (value) nickname.value = value.player.nickname
})

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
    <StateBlock :loading="loading" :error="error">
      <template v-if="data">
        <div class="profile-top">
          <div>
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
            <div class="row" style="gap: 14px">
              <PlayerAvatar :url="data.player.avatar_url" :size="72" :alt="data.player.nickname" />
              <div class="stack" style="gap: 4px">
                <h1>{{ data.player.nickname }}</h1>
                <span v-if="data.player.status === 'blocked'" class="badge tone-red">Заблокирован</span>
              </div>
            </div>

            <div class="tiles">
              <div class="tile">
                <b>{{ data.rating.display_place === null ? '—' : `№${data.rating.display_place}` }}</b>
                <span>Место<template v-if="data.rating.is_special"> · Спецместо</template></span>
              </div>
              <div class="tile"><b>{{ data.rating.points }}</b><span>Очки</span></div>
              <div class="tile"><b>{{ data.stats.fights }}</b><span>Бои</span></div>
              <div class="tile"><b>{{ data.stats.wins }}</b><span>Победы</span></div>
              <div class="tile"><b>{{ data.stats.losses }}</b><span>Поражения</span></div>
              <div class="tile"><b>{{ data.stats.win_rate === null ? '—' : `${data.stats.win_rate}%` }}</b><span>Процент побед</span></div>
              <div class="tile"><b>{{ data.stats.best_streak }}</b><span>Лучшая серия</span></div>
            </div>

            <div class="grid" style="grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr))">
              <div class="card stack">
                <h3>Злейший враг</h3>
                <div v-for="item in data.stats.nemeses" :key="item.player.id" class="row between">
                  <PlayerChip :player="item.player" />
                  <span class="small muted">Поражений: {{ item.count }}</span>
                </div>
                <p v-if="!data.stats.nemeses.length" class="small muted">Поражений пока не было</p>
              </div>
              <div class="card stack">
                <h3>Кого чаще всего побеждал</h3>
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

        <section class="section">
          <h2>Активные пояса</h2>
          <div v-if="data.belts.active.length" class="grid">
            <div v-for="item in data.belts.active" :key="item.belt.id" class="card belt-row">
              <BeltIcon :belt="item.belt" :size="56" />
              <div class="stack" style="gap: 4px; min-width: 0">
                <span class="badge tone-gold">{{ item.caption }}</span>
                <RouterLink class="link" :to="`/belts/${item.belt.id}`">{{ item.belt.name }}</RouterLink>
                <ul class="small muted" style="margin: 0; padding-left: 16px">
                  <li v-for="win in item.wins" :key="win.id">
                    {{ formatDate(win.won_at) }}{{ win.is_defense ? ', защита' : '' }} —
                    <RouterLink v-if="win.tournament" class="link" :to="`/tournaments/${win.tournament.id}`">{{ win.tournament.title }}</RouterLink>
                    <RouterLink v-else class="link" :to="`/fights/${win.fight_id}`">титульный бой</RouterLink>
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <p v-else class="empty">Активных поясов нет.</p>
        </section>

        <section class="section">
          <h2>Прошлые пояса</h2>
          <div v-if="data.belts.past.length" class="grid">
            <div v-for="item in data.belts.past" :key="item.belt.id" class="card belt-row">
              <BeltIcon :belt="item.belt" past :size="56" />
              <div class="stack" style="gap: 4px; min-width: 0">
                <span class="badge plain tone-grey" style="white-space: normal">{{ item.caption }}</span>
                <ul class="small muted" style="margin: 0; padding-left: 16px">
                  <li v-for="win in item.wins" :key="win.id">
                    {{ formatDate(win.won_at) }}{{ win.is_defense ? ', защита' : '' }} —
                    <RouterLink v-if="win.tournament" class="link" :to="`/tournaments/${win.tournament.id}`">{{ win.tournament.title }}</RouterLink>
                    <RouterLink v-else class="link" :to="`/fights/${win.fight_id}`">титульный бой</RouterLink>
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <p v-else class="empty">Прошлых поясов нет.</p>
        </section>

        <section class="section">
          <h2>История боёв</h2>
          <div v-if="history.data.value?.length" class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Соперник</th>
                  <th>Исход</th>
                  <th class="hide-sm">Тип</th>
                  <th class="hide-sm">Способ</th>
                  <th class="num">Очки</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in history.data.value" :key="item.fight_id">
                  <td class="small"><RouterLink class="link" :to="`/fights/${item.fight_id}`">{{ formatDateTime(item.fought_at) }}</RouterLink></td>
                  <td>
                    <PlayerChip :player="item.opponent" :size="24" />
                    <div class="show-sm small muted">
                      {{ fightKindLabel[item.kind] }}<template v-if="resultLine(item.method, item.round)"> · {{ resultLine(item.method, item.round) }}</template>
                      <template v-if="item.tournament"> · <RouterLink class="link" :to="`/tournaments/${item.tournament.id}`">{{ item.tournament.title }}</RouterLink></template>
                    </div>
                  </td>
                  <td>
                    <span class="badge" :class="item.outcome === 'win' ? 'tone-green' : 'tone-red'">{{ item.outcome === 'win' ? 'Победа' : 'Поражение' }}</span>
                  </td>
                  <td class="hide-sm small">
                    {{ fightKindLabel[item.kind] }}
                    <RouterLink v-if="item.tournament" class="link" :to="`/tournaments/${item.tournament.id}`">{{ item.tournament.title }}</RouterLink>
                  </td>
                  <td class="hide-sm small">{{ resultLine(item.method, item.round) || '—' }}</td>
                  <td class="num">
                    <span :class="(item.auto_delta ?? 0) > 0 ? 'delta-up' : 'delta-down'">{{ signed(item.auto_delta ?? 0) }}</span>
                    <span v-if="item.manual_delta" class="small muted"> ({{ signed(item.manual_delta) }} вручную)</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="empty">Подтверждённых боёв пока нет.</p>
        </section>
      </template>
    </StateBlock>
  </main>
</template>
