<script setup lang="ts">
import { RouterLink } from 'vue-router'
import PlayerAvatar from './PlayerAvatar.vue'
import type { PlayerBrief } from '../types'

withDefaults(defineProps<{ player: PlayerBrief; size?: number }>(), { size: 28 })
</script>

<template>
  <RouterLink class="player-chip" :to="`/players/${player.id}`">
    <PlayerAvatar :url="player.avatar_url" :size="size" :alt="player.nickname" />
    <span class="name">{{ player.nickname }}</span>
  </RouterLink>
</template>
