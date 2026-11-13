<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { currentUser } from '../auth'
import { useAction } from '../feedback'
import { formatBoutDate } from '../format'
import FightResultForm from './FightResultForm.vue'
import Modal from './Modal.vue'
import type { FightBrief, ResultPayload } from '../types'

const props = defineProps<{ fight: FightBrief }>()
const emit = defineEmits<{ changed: [] }>()

const { busy, run } = useAction()

/** Кого ждём по раннему бою; если ход за самим зрителем — «вас». */
const waitingNames = computed(() =>
  (props.fight.blocked_by?.waiting_for ?? [])
    .map((player) => (player.id === currentUser.value?.id ? 'вас' : player.nickname))
    .join(', '),
)
const disputeOpen = ref(false)
const correctOpen = ref(false)
const reason = ref('')

async function confirm(): Promise<void> {
  const done = await run(
    () => api.post(`/fights/${props.fight.id}/confirm`, { version_no: props.fight.version_no }),
    'Результат подтверждён',
  )
  if (done) emit('changed')
}

async function dispute(): Promise<void> {
  const done = await run(
    () => api.post(`/fights/${props.fight.id}/dispute`, { version_no: props.fight.version_no, reason: reason.value }),
    'Результат оспорен',
  )
  if (done) {
    disputeOpen.value = false
    emit('changed')
  }
}

async function correct(payload: ResultPayload): Promise<void> {
  const done = await run(
    () => api.post(`/fights/${props.fight.id}/correct`, { ...payload, expected_version: props.fight.version_no }),
    'Исправленная версия отправлена',
  )
  if (done) {
    correctOpen.value = false
    emit('changed')
  }
}
</script>

<template>
  <p v-if="fight.backdated && (fight.can_confirm || fight.can_correct)" class="bout-blocked small">
    Бой сыгран раньше уже подтверждённого боя игрока {{ fight.backdated.player.nickname }} (от {{ formatBoutDate(fight.backdated.latest_fought_at) }}),
    поэтому подтвердить его нельзя: очки считаются по порядку.
    {{ fight.can_correct ? 'Исправьте дату в записи' : 'Оспорьте запись, чтобы автор исправил дату,' }} или попросите администратора отменить бой.
  </p>
  <p v-else-if="fight.blocked_by && fight.can_confirm" class="bout-blocked small">
    Подтвердить можно после итога более раннего боя
    <RouterLink class="link" :to="`/fights/${fight.blocked_by.fight_id}`">
      {{ fight.blocked_by.player1.nickname }} — {{ fight.blocked_by.player2.nickname }} от {{ formatBoutDate(fight.blocked_by.fought_at) }}</RouterLink>.
    Ждём: {{ waitingNames }}.
  </p>
  <div v-if="fight.can_confirm || fight.can_dispute || fight.can_correct" class="row">
    <button v-if="fight.can_confirm" class="btn primary" :disabled="busy || Boolean(fight.blocked_by) || Boolean(fight.backdated)" @click="confirm">Подтвердить</button>
    <button v-if="fight.can_dispute" class="btn danger" :disabled="busy" @click="disputeOpen = true">Оспорить</button>
    <button v-if="fight.can_correct" class="btn primary" :disabled="busy" @click="correctOpen = true">Исправить запись</button>
  </div>

  <Modal v-if="disputeOpen" title="Оспорить результат" @close="disputeOpen = false">
    <form class="stack" @submit.prevent="dispute">
      <label class="field">
        Причина
        <textarea v-model="reason" required minlength="3" maxlength="500" placeholder="Что в записи неверно"></textarea>
      </label>
      <button class="btn danger" type="submit" :disabled="busy">Оспорить</button>
    </form>
  </Modal>

  <Modal v-if="correctOpen" title="Исправить запись" @close="correctOpen = false">
    <p class="small muted">Старые подтверждения перестанут действовать, новую версию снова подтверждают оба игрока.</p>
    <FightResultForm :player1="fight.player1" :player2="fight.player2" :initial="fight" :busy="busy" @submit="correct" />
  </Modal>
</template>
