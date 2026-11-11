<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { currentUser } from '../auth'
import FightResultForm from '../components/FightResultForm.vue'
import StateBlock from '../components/StateBlock.vue'
import { useAction, useLoad } from '../feedback'
import { fromLocalInput, requestId, toLocalInput } from '../format'
import type { FightDetail, PlayerBrief, ResultPayload, UpcomingBout } from '../types'

const router = useRouter()
const route = useRoute()
const { data, error, loading } = useLoad(() => api.get<PlayerBrief[]>('/players/options'))
const { busy, run } = useAction()
const mode = ref<'played' | 'planned'>('played')
// Ссылка «Записать бой» со страницы бойца передаёт соперника в ?opponent=.
const opponentId = ref<number | ''>(Number(route.query.opponent) || '')
const scheduledAt = ref('')
const earliest = toLocalInput(new Date())
// Один ключ на открытую форму: повторная отправка вернёт уже созданную запись.
const clientRequestId = requestId()

const options = computed(() => (data.value ?? []).filter((player) => player.id !== currentUser.value?.id))
const opponent = computed(() => options.value.find((player) => player.id === opponentId.value) ?? null)
const me = computed<PlayerBrief | null>(() =>
  currentUser.value
    ? {
        id: currentUser.value.id,
        nickname: currentUser.value.nickname,
        avatar_url: currentUser.value.avatar_url,
        status: currentUser.value.status,
      }
    : null,
)

async function submit(payload: ResultPayload): Promise<void> {
  const fight = await run(
    () =>
      api.post<FightDetail>('/fights', {
        ...payload,
        opponent_id: opponentId.value,
        client_request_id: clientRequestId,
      }),
    'Бой отправлен сопернику на подтверждение',
  )
  if (fight) await router.push(`/fights/${fight.id}`)
}

async function plan(): Promise<void> {
  const created = await run(
    () =>
      api.post<UpcomingBout>('/fights/planned', {
        opponent_id: opponentId.value,
        scheduled_at: fromLocalInput(scheduledAt.value),
        client_request_id: clientRequestId,
      }),
    'Бой запланирован',
  )
  if (created) await router.push('/fights')
}
</script>

<template>
  <main class="container page" style="max-width: 620px">
    <h1>Записать бой</h1>
    <p class="muted">
      {{
        mode === 'played'
          ? 'Запись попадёт в историю и рейтинг, когда её подтвердит соперник.'
          : 'Бой появится в предстоящих, зрители смогут голосовать. Результат внесёте после игры.'
      }}
    </p>
    <StateBlock :loading="loading" :error="error" skeleton="form">
      <section class="card stack">
        <div class="choice-group" role="radiogroup" aria-label="Когда проходит бой" data-tour="fight-mode">
          <label class="choice"><input v-model="mode" type="radio" name="mode" value="played" /> Бой уже прошёл</label>
          <label class="choice"><input v-model="mode" type="radio" name="mode" value="planned" /> Бой ещё не состоялся</label>
        </div>
        <label class="field" data-tour="fight-opponent">
          Соперник
          <select v-model="opponentId">
            <option value="" disabled>Выберите соперника</option>
            <option v-for="player in options" :key="player.id" :value="player.id">{{ player.nickname }}</option>
          </select>
        </label>
        <template v-if="opponent && me">
          <FightResultForm v-if="mode === 'played'" :key="opponent.id" :player1="me" :player2="opponent" :busy="busy" @submit="submit" />
          <form v-else class="stack" @submit.prevent="plan">
            <label class="field">
              Дата и время боя
              <input v-model="scheduledAt" type="datetime-local" :min="earliest" required />
            </label>
            <button class="btn primary" type="submit" :disabled="busy">Запланировать бой</button>
          </form>
        </template>
      </section>
    </StateBlock>
  </main>
</template>
