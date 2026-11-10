<script setup lang="ts">
import { RouterLink } from 'vue-router'
import BeltIcon from './BeltIcon.vue'
import PlayerAvatar from './PlayerAvatar.vue'
import StatusBadge from './StatusBadge.vue'
import { formatDateTime, promoTypeLabel, seatsLine, tournamentCta } from '../format'
import type { Promo } from '../types'

defineProps<{ promo: Promo }>()
</script>

<template>
  <article class="card promo">
    <template v-if="promo.type === 'tournament' && promo.tournament">
      <div class="promo-media">
        <img v-if="promo.image_url" :src="promo.image_url" :alt="promo.title" />
        <BeltIcon v-else :belt="promo.tournament.belt" :size="72" />
      </div>
      <div class="promo-body">
        <span class="kicker">{{ promoTypeLabel[promo.type] }}</span>
        <h3>{{ promo.title }}</h3>
        <p v-if="promo.description" class="small muted">{{ promo.description }}</p>
        <div class="row between" style="margin-top: auto">
          <StatusBadge :tournament="promo.tournament.status" />
          <span class="small muted">Мест занято: {{ seatsLine(promo.tournament) }}</span>
        </div>
        <RouterLink class="btn primary" :to="`/tournaments/${promo.tournament.id}`">{{ tournamentCta(promo.tournament) }}</RouterLink>
      </div>
    </template>

    <template v-else-if="promo.type === 'fight_announcement' && promo.fighter1 && promo.fighter2">
      <div class="promo-versus">
        <RouterLink :to="`/players/${promo.fighter1.id}`">
          <PlayerAvatar :url="promo.fighter1.avatar_url" :size="64" :alt="promo.fighter1.nickname" />
          {{ promo.fighter1.nickname }}
        </RouterLink>
        <span class="vs">VS</span>
        <RouterLink :to="`/players/${promo.fighter2.id}`">
          <PlayerAvatar :url="promo.fighter2.avatar_url" :size="64" :alt="promo.fighter2.nickname" />
          {{ promo.fighter2.nickname }}
        </RouterLink>
      </div>
      <div class="promo-body">
        <span class="kicker">{{ promoTypeLabel[promo.type] }}</span>
        <h3>{{ promo.title }}</h3>
        <p v-if="promo.description" class="small muted">{{ promo.description }}</p>
        <p v-if="promo.fight_at" class="small" style="margin-top: auto">{{ formatDateTime(promo.fight_at) }}</p>
      </div>
    </template>

    <template v-else-if="promo.type === 'fighter_of_week' && promo.player">
      <div class="promo-versus" style="grid-template-columns: 1fr">
        <RouterLink :to="`/players/${promo.player.id}`">
          <PlayerAvatar :url="promo.player.avatar_url" :size="84" :alt="promo.player.nickname" />
          {{ promo.player.nickname }}
        </RouterLink>
      </div>
      <div class="promo-body">
        <span class="kicker">{{ promoTypeLabel[promo.type] }}</span>
        <h3>{{ promo.title }}</h3>
        <p v-if="promo.description" class="small muted">{{ promo.description }}</p>
        <RouterLink class="btn" style="margin-top: auto" :to="`/players/${promo.player.id}`">Профиль бойца</RouterLink>
      </div>
    </template>
  </article>
</template>
