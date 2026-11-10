<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { currentUser } from '../auth'
import FightResultForm from '../components/FightResultForm.vue'
import StateBlock from '../components/StateBlock.vue'
import { useAction, useLoad } from '../feedback'
import { requestId } from '../format'
import type { FightDetail, PlayerBrief, ResultPayload } from '../types'

const router = useRouter()
const { data, error, loading } = useLoad(() => api.get<PlayerBrief[]>('/players/options'))
const { busy, run } = useAction()
const opponentId = ref<number | ''>('')
// Один ключ на открытую форму: повторная отправка вернёт уже созданный бой.
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
</script>

<template>
  <main class="container page" style="max-width: 620px">
    <h1>Записать бой</h1>
    <p class="muted">Запись создаётся после игры. Она попадёт в историю и рейтинг, когда её подтвердит соперник.</p>
    <StateBlock :loading="loading" :error="error">
      <section class="card stack">
        <label class="field">
          Соперник
          <select v-model="opponentId">
            <option value="" disabled>Выберите соперника</option>
            <option v-for="player in options" :key="player.id" :value="player.id">{{ player.nickname }}</option>
          </select>
        </label>
        <FightResultForm v-if="opponent && me" :key="opponent.id" :player1="me" :player2="opponent" :busy="busy" @submit="submit" />
      </section>
    </StateBlock>
  </main>
</template>
