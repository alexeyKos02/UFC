<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import FightActions from './FightActions.vue'
import FighterPhoto from './FighterPhoto.vue'
import StatusBadge from './StatusBadge.vue'
import { boutCaption, formatBoutDate, formatDateTime, methodLabel, resultLine, signed } from '../format'
import type { FightDetail } from '../types'

const props = defineProps<{ fight: FightDetail; collapsible?: boolean }>()
const emit = defineEmits<{ changed: []; collapse: [] }>()

interface DuelRow {
  label: string
  left: number
  right: number
  leftText: string
  rightText: string
  hasBar: boolean
}

function row(label: string, values: [number, number], format: (value: number) => string = String, hasBar = true): DuelRow {
  return {
    label,
    left: values[0],
    right: values[1],
    leftText: format(values[0]),
    rightText: format(values[1]),
    hasBar,
  }
}

const caption = computed(() => {
  const base = boutCaption[props.fight.kind]
  return props.fight.is_title_defense ? `${base} · Защита пояса` : base
})

const duels = computed<DuelRow[]>(() => {
  const { fight } = props
  const rows: DuelRow[] = []
  const first = fight.rating_changes.find((change) => change.player.id === fight.player1.id)
  const second = fight.rating_changes.find((change) => change.player.id === fight.player2.id)
  if (first && second) {
    rows.push(row('Место до боя', [first.place_before, second.place_before], (place) => `№${place}`, false))
    rows.push(row('Место после боя', [first.place_after, second.place_after], (place) => `№${place}`, false))
    rows.push(row('Очки до боя', [first.points_before, second.points_before]))
    if (fight.adjustment) {
      rows.push(row('Ручная корректировка', [manual(fight.player1.id), manual(fight.player2.id)], signed))
    }
    rows.push(row('Очки после боя', [first.points_after + manual(fight.player1.id), second.points_after + manual(fight.player2.id)]))
  }
  if (fight.votes) {
    rows.push(row('Голоса зрителей', [fight.votes.first, fight.votes.second]))
  }
  if (fight.comparison) {
    rows.push(row('Личные встречи', fight.comparison.head_to_head))
    rows.push(row('Победы в лиге', fight.comparison.league_wins))
    rows.push(row('Поражения в лиге', fight.comparison.league_losses))
  }
  return rows
})

/** Ручная корректировка для игрока: у победителя winner_delta, у проигравшего — loser_delta. */
function manual(playerId: number): number {
  const adjustment = props.fight.adjustment
  if (!adjustment) return 0
  return playerId === props.fight.winner_id ? adjustment.winner_delta : adjustment.loser_delta
}

function positive(value: number): number {
  return Math.max(0, value)
}
</script>

<template>
  <article class="bout bout-full">
    <button v-if="collapsible" class="bout-toggle" aria-label="Свернуть бой" :aria-expanded="true" @click="emit('collapse')">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M20 4l-7 7M13 5v6h6M4 20l7-7M11 19v-6H5" />
      </svg>
    </button>

    <header class="bout-head">
      <RouterLink class="bout-name first" :to="`/players/${fight.player1.id}`">{{ fight.player1.nickname }}</RouterLink>
      <p class="bout-caption">{{ caption }}</p>
      <RouterLink class="bout-name second" :to="`/players/${fight.player2.id}`">{{ fight.player2.nickname }}</RouterLink>
    </header>
    <div class="bout-line" aria-hidden="true"><i class="corner-red"></i><i class="corner-blue"></i></div>

    <div class="bout-body">
      <div class="bout-figure first">
        <FighterPhoto :fighter="fight.player1" side="first" :winner="fight.winner_id === fight.player1.id" :delta="fight.points_change?.[0]" />
      </div>

      <div class="bout-sheet">
        <div class="bout-meta">
          <StatusBadge :fight="fight.status" />
          <span>Бой #{{ fight.id }}</span>
          <span>Версия {{ fight.version_no }}</span>
          <RouterLink v-if="fight.tournament" class="link" :to="`/tournaments/${fight.tournament.id}`">{{ fight.tournament.title }}</RouterLink>
          <RouterLink v-if="collapsible" class="link" :to="`/fights/${fight.id}`">Страница боя</RouterLink>
        </div>

        <dl class="bout-facts bout-box">
          <div><dt>Раунд</dt><dd>{{ fight.round ?? '—' }}</dd></div>
          <div><dt>Дата</dt><dd>{{ formatBoutDate(fight.fought_at) }}</dd></div>
          <div><dt>Метод</dt><dd>{{ fight.method ? methodLabel[fight.method] : '—' }}</dd></div>
        </dl>

        <p v-if="fight.dispute_reason" class="bout-note-inline tone-red">Причина спора: {{ fight.dispute_reason }}</p>
        <FightActions :fight="fight" @changed="emit('changed')" />

        <div v-for="item in duels" :key="item.label" class="duel">
          <div class="duel-head">
            <b>{{ item.leftText }}</b>
            <span class="duel-label">{{ item.label }}</span>
            <b>{{ item.rightText }}</b>
          </div>
          <div class="duel-bar" role="img" :aria-label="`${item.label}: ${fight.player1.nickname} ${item.leftText}, ${fight.player2.nickname} ${item.rightText}`">
            <template v-if="item.hasBar && positive(item.left) + positive(item.right) > 0">
              <i v-if="positive(item.left)" class="corner-red" :style="{ flexGrow: positive(item.left) }" :title="`${fight.player1.nickname}: ${item.leftText}`"></i>
              <i v-if="positive(item.right)" class="corner-blue" :style="{ flexGrow: positive(item.right) }" :title="`${fight.player2.nickname}: ${item.rightText}`"></i>
            </template>
            <i v-else class="duel-neutral"></i>
          </div>
        </div>

        <p v-if="fight.adjustment" class="preview">Причина ручной корректировки: {{ fight.adjustment.reason }}</p>

        <details class="bout-versions" :open="fight.versions.length > 1">
          <summary>История версий: {{ fight.versions.length }}</summary>
          <article v-for="version in [...fight.versions].reverse()" :key="version.version_no" class="stack bout-version">
            <div class="row between">
              <b>Версия {{ version.version_no }}<template v-if="version.version_no === fight.version_no"> (текущая)</template></b>
              <span class="small muted">{{ formatDateTime(version.created_at) }}</span>
            </div>
            <p class="small">
              Победитель: {{ version.winner.nickname }}. Бой: {{ formatDateTime(version.fought_at) }}<template v-if="resultLine(version.method, version.round)">. {{ resultLine(version.method, version.round) }}</template>.
            </p>
            <p class="small muted">
              Внёс: {{ version.submitted_by.nickname }}. Подтвердили: {{ version.confirmed_by.map((player) => player.nickname).join(', ') || 'никто' }}.
            </p>
            <p v-if="version.dispute_reason" class="small tone-red">Оспорил {{ version.disputed_by?.nickname }}: {{ version.dispute_reason }}</p>
          </article>
        </details>
      </div>

      <div class="bout-figure second">
        <FighterPhoto :fighter="fight.player2" side="second" :winner="fight.winner_id === fight.player2.id" :delta="fight.points_change?.[1]" />
      </div>
    </div>
  </article>
</template>
