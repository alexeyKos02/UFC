<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { currentUser } from '../auth'
import { formatDate, methodLabel, plural, signed } from '../format'
import type { HeadToHead, MethodKey, PlayerBrief } from '../types'
import PlayerAvatar from './PlayerAvatar.vue'

const props = defineProps<{ h2h: HeadToHead; rival: PlayerBrief }>()
// Сначала виден только счёт, подробности — по нажатию.
const expanded = ref(false)

const METHODS: { key: MethodKey; label: string }[] = [
  { key: 'ko_tko', label: methodLabel.ko_tko },
  { key: 'submission', label: methodLabel.submission },
  { key: 'decision', label: methodLabel.decision },
  { key: 'none', label: 'Способ не указан' },
]

const share = computed(() => (props.h2h.fights ? Math.round((props.h2h.my_wins * 100) / props.h2h.fights) : 50))
const methods = computed(() =>
  METHODS.map((item) => ({ ...item, mine: props.h2h.methods.mine[item.key] ?? 0, theirs: props.h2h.methods.theirs[item.key] ?? 0 })).filter(
    (item) => item.mine || item.theirs,
  ),
)
const streakText = computed(() => {
  const streak = props.h2h.streak
  if (!streak) return ''
  const who = streak.mine ? 'вы' : props.rival.nickname
  if (streak.count === 1) return `Последняя победа: ${who}`
  return `${streak.mine ? 'Вы' : who}: ${streak.count} ${plural(streak.count, ['победа', 'победы', 'побед'])} подряд`
})

function resultLine(item: HeadToHead['recent'][number]): string {
  const parts = [item.method ? methodLabel[item.method] : '', item.round ? `${item.round} раунд` : ''].filter(Boolean)
  return parts.join(', ') || 'Способ не указан'
}
</script>

<template>
  <section class="card h2h" aria-labelledby="h2h-title">
    <div class="row between">
      <h2 id="h2h-title">Очные встречи</h2>
      <span v-if="h2h.fights" class="small muted">{{ h2h.fights }} {{ plural(h2h.fights, ['бой', 'боя', 'боёв']) }}</span>
    </div>

    <template v-if="h2h.fights">
      <div class="h2h-score">
        <div class="h2h-side">
          <PlayerAvatar :url="currentUser?.avatar_url ?? null" :size="36" />
          <span>Вы</span>
        </div>
        <div class="h2h-numbers" :aria-label="`Счёт ${h2h.my_wins}:${h2h.their_wins}`">
          <b :class="{ lead: h2h.my_wins > h2h.their_wins }">{{ h2h.my_wins }}</b>
          <span>:</span>
          <b :class="{ lead: h2h.their_wins > h2h.my_wins }">{{ h2h.their_wins }}</b>
        </div>
        <div class="h2h-side right">
          <span class="h2h-rival">{{ rival.nickname }}</span>
          <PlayerAvatar :url="rival.avatar_url" :size="36" />
        </div>
      </div>
      <div class="h2h-bar" aria-hidden="true"><span :style="{ width: `${share}%` }" /></div>

      <button
        class="h2h-toggle"
        type="button"
        :aria-expanded="expanded"
        aria-controls="h2h-details"
        @click="expanded = !expanded"
      >
        {{ expanded ? 'Свернуть' : 'Подробнее' }}
        <span class="h2h-chevron" :class="{ open: expanded }" aria-hidden="true">▾</span>
      </button>

      <div v-show="expanded" id="h2h-details" class="h2h-details">
      <div class="h2h-facts">
        <div v-if="streakText" class="h2h-fact">
          <span class="small muted">Текущая серия</span>
          <b>{{ streakText }}</b>
        </div>
        <div class="h2h-fact">
          <span class="small muted">Очки рейтинга в этих боях</span>
          <b :class="h2h.points > 0 ? 'tone-plus' : h2h.points < 0 ? 'tone-minus' : ''">{{ signed(h2h.points) }}</b>
        </div>
      </div>

      <table v-if="methods.length" class="h2h-methods">
        <thead>
          <tr><th>Способ победы</th><th class="num">Вы</th><th class="num">{{ rival.nickname }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in methods" :key="item.key">
            <td>{{ item.label }}</td>
            <td class="num">{{ item.mine }}</td>
            <td class="num">{{ item.theirs }}</td>
          </tr>
        </tbody>
      </table>

      <div class="stack" style="gap: 6px">
        <span class="small muted">Последние встречи</span>
        <RouterLink v-for="item in h2h.recent" :key="item.fight_id" class="h2h-recent" :to="`/fights/${item.fight_id}`">
          <span class="badge" :class="item.won ? 'tone-green' : 'tone-red'">{{ item.won ? 'Победа' : 'Поражение' }}</span>
          <span class="small">{{ resultLine(item) }}</span>
          <span class="small muted h2h-date">{{ formatDate(item.fought_at) }}</span>
        </RouterLink>
      </div>
      <RouterLink class="btn sm" style="align-self: flex-start" :to="`/fights/new?opponent=${rival.id}`">Записать новый бой</RouterLink>
      </div>
    </template>

    <template v-else>
      <p class="muted" style="margin: 0">Вы с {{ rival.nickname }} ещё не встречались.</p>
      <RouterLink class="btn primary" style="align-self: flex-start" :to="`/fights/new?opponent=${rival.id}`">Записать бой</RouterLink>
    </template>
  </section>
</template>
