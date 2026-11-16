<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { currentUser } from '../auth'
import { useAction } from '../feedback'
import Modal from './Modal.vue'
import PlayerChip from './PlayerChip.vue'
import ResultSubmit from './ResultSubmit.vue'
import StatusBadge from './StatusBadge.vue'
import WalkoverForm from './WalkoverForm.vue'
import type { MatchOut, PlayerBrief } from '../types'

/**
 * Карточка матча турнирной сетки: игроки с отметкой победителя, состояние и действие.
 * Админ и владелец могут присудить техническую победу (соперник не явился) или отменить её.
 */
const props = defineProps<{ match: MatchOut; tournamentRunning: boolean }>()
const emit = defineEmits<{ done: [] }>()

const slots = computed<(PlayerBrief | null)[]>(() => [props.match.player1, props.match.player2])
const isMine = computed(() => slots.value.some((player) => player && player.id === currentUser.value?.id))
const winnerMark = computed(() => (props.match.is_bye ? 'Проход' : props.match.is_walkover ? 'Тех. победа' : 'Победа'))

const walkoverOpen = ref(false)
const cancelOpen = ref(false)
const { busy, run } = useAction()

function onWalkover(): void {
  walkoverOpen.value = false
  emit('done')
}

async function cancelWalkover(): Promise<void> {
  if (await run(() => api.post(`/admin/tournaments/matches/${props.match.id}/walkover/cancel`), 'Техническая победа отменена')) {
    cancelOpen.value = false
    emit('done')
  }
}
</script>

<template>
  <article
    class="match"
    :class="{ mine: isMine && tournamentRunning && match.state !== 'completed' && match.state !== 'bye' && match.state !== 'walkover' }"
    :data-match-id="match.id"
  >
    <div v-for="(slot, index) in slots" :key="index" class="match-player">
      <PlayerChip v-if="slot" :player="slot" :size="24" :class="{ 'is-loser': match.winner_id && match.winner_id !== slot.id }" />
      <span v-else class="tbd small">{{ match.is_bye ? 'Без соперника' : 'Определится позже' }}</span>
      <span v-if="slot && match.winner_id === slot.id" class="winner-mark" :title="match.walkover_reason ?? undefined">{{ winnerMark }}</span>
    </div>
    <div class="match-foot">
      <StatusBadge :match="match.state" />
      <ResultSubmit
        v-if="match.can_submit && match.player1 && match.player2"
        compact
        :url="`/tournaments/matches/${match.id}/result`"
        :player1="match.player1"
        :player2="match.player2"
        @done="emit('done')"
      />
      <RouterLink v-else-if="match.fight_id && (isMine || match.state === 'completed')" class="link small" :to="`/fights/${match.fight_id}`">Открыть бой</RouterLink>
    </div>
    <p v-if="match.is_walkover && match.walkover_reason" class="match-note small muted">Без боя: {{ match.walkover_reason }}</p>
    <div v-if="match.can_walkover || match.can_cancel_walkover" class="match-admin">
      <button v-if="match.can_walkover" class="btn sm" type="button" @click="walkoverOpen = true">Тех. победа</button>
      <button v-if="match.can_cancel_walkover" class="btn sm" type="button" @click="cancelOpen = true">Отменить тех. победу</button>
    </div>
  </article>

  <Modal v-if="walkoverOpen" title="Техническая победа" @close="walkoverOpen = false">
    <WalkoverForm :match="match" @done="onWalkover" />
  </Modal>
  <Modal v-if="cancelOpen" title="Отменить техническую победу" @close="cancelOpen = false">
    <div class="stack">
      <p class="small">
        Матч снова будет ждать результата. Если победитель уже играл следующий круг, сначала удалите или отмените тот бой.
      </p>
      <button class="btn danger" type="button" :disabled="busy" @click="cancelWalkover">Отменить техническую победу</button>
    </div>
  </Modal>
</template>
