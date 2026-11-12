<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import FightActions from './FightActions.vue'
import FightExpanded from './FightExpanded.vue'
import FighterPhoto from './FighterPhoto.vue'
import StatusBadge from './StatusBadge.vue'
import { useAction } from '../feedback'
import { boutCaption, formatBoutDate, methodLabel } from '../format'
import type { FightBrief, FightDetail } from '../types'

const props = defineProps<{ fight: FightBrief; actions?: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const { busy, run } = useAction()
const detail = ref<FightDetail | null>(null)
const expanded = ref(false)

const hasActions = computed(
  () => props.actions && (props.fight.can_confirm || props.fight.can_dispute || props.fight.can_correct),
)

// У боя без голосования (записан сразу, без анонса) голосов просто нет — показываем нули.
const votes = computed(() => props.fight.votes ?? { first: 0, second: 0 })

function fetchDetail(): Promise<FightDetail | undefined> {
  return run(() => api.get<FightDetail>(`/fights/${props.fight.id}`))
}

async function expand(): Promise<void> {
  const loaded = await fetchDetail()
  if (loaded) {
    detail.value = loaded
    expanded.value = true
  }
}

async function onChanged(): Promise<void> {
  const loaded = await fetchDetail()
  if (loaded) detail.value = loaded
  emit('changed')
}
</script>

<template>
  <FightExpanded v-if="expanded && detail" :fight="detail" collapsible @collapse="expanded = false" @changed="onChanged" />
  <article v-else class="bout">
    <button class="bout-toggle" aria-label="Развернуть бой" :aria-expanded="false" :disabled="busy" @click="expand">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7" />
      </svg>
    </button>

    <div class="bout-main">
      <div class="bout-photo first">
        <FighterPhoto :fighter="fight.player1" side="first" :winner="fight.winner_id === fight.player1.id" :delta="fight.points_change?.[0]" />
      </div>

      <div class="bout-center">
        <p class="bout-caption">{{ boutCaption[fight.kind] }}</p>
        <div class="bout-names">
          <RouterLink class="bout-name first" :to="`/players/${fight.player1.id}`">{{ fight.player1.nickname }}</RouterLink>
          <span class="bout-vs">VS</span>
          <RouterLink class="bout-name second" :to="`/players/${fight.player2.id}`">{{ fight.player2.nickname }}</RouterLink>
        </div>
        <dl class="bout-facts">
          <div><dt>Раунд</dt><dd>{{ fight.round ?? '—' }}</dd></div>
          <div><dt>Дата</dt><dd>{{ formatBoutDate(fight.fought_at) }}</dd></div>
          <div><dt>Метод</dt><dd>{{ fight.method ? methodLabel[fight.method] : '—' }}</dd></div>
        </dl>
      </div>

      <div class="bout-photo second">
        <FighterPhoto :fighter="fight.player2" side="second" :winner="fight.winner_id === fight.player2.id" :delta="fight.points_change?.[1]" />
      </div>
    </div>

    <div class="bout-strip">
      <div><StatusBadge :fight="fight.status" /></div>
      <div class="bout-strip-center">
        <div class="bout-points" :aria-label="`Голоса зрителей: ${votes.first} и ${votes.second}`">
          <b>{{ votes.first }}</b>
          <span>Голоса</span>
          <b>{{ votes.second }}</b>
        </div>
      </div>
      <div class="bout-strip-end">
        <RouterLink v-if="fight.tournament" class="link small" :to="`/tournaments/${fight.tournament.id}`">{{ fight.tournament.title }}</RouterLink>
      </div>
    </div>

    <p v-if="fight.dispute_reason" class="bout-note tone-red">Причина спора: {{ fight.dispute_reason }}</p>
    <div v-if="hasActions" class="bout-actions">
      <FightActions :fight="fight" @changed="emit('changed')" />
    </div>
  </article>
</template>
