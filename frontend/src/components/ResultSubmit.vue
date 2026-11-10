<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'
import { useAction } from '../feedback'
import FightResultForm from './FightResultForm.vue'
import Modal from './Modal.vue'
import type { PlayerBrief, ResultPayload } from '../types'

const props = defineProps<{ url: string; player1: PlayerBrief; player2: PlayerBrief; compact?: boolean }>()
const emit = defineEmits<{ done: [] }>()
const { busy, run } = useAction()
const open = ref(false)

async function submit(payload: ResultPayload): Promise<void> {
  if (await run(() => api.post(props.url, payload), 'Результат отправлен сопернику на подтверждение')) {
    open.value = false
    emit('done')
  }
}
</script>

<template>
  <button class="btn primary" :class="{ sm: compact }" @click="open = true">Внести результат</button>
  <Modal v-if="open" title="Результат боя" @close="open = false">
    <FightResultForm :player1="player1" :player2="player2" :busy="busy" @submit="submit" />
  </Modal>
</template>
