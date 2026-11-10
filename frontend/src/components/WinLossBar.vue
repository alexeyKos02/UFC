<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ wins: number; losses: number; winRate: number | null }>()

const fights = computed(() => props.wins + props.losses)
const summary = computed(
  () => `Победы: ${props.wins}, поражения: ${props.losses}, процент побед: ${props.winRate ?? 0}%`,
)
</script>

<template>
  <section class="record" aria-label="Статистика боёв">
    <template v-if="fights">
      <div class="record-labels">
        <span class="record-label"><i class="record-swatch record-wins" aria-hidden="true"></i>Победы <b>{{ wins }}</b></span>
        <span>Боёв <b>{{ fights }}</b> · Побед <b>{{ winRate }}%</b></span>
        <span class="record-label"><i class="record-swatch record-losses" aria-hidden="true"></i>Поражения <b>{{ losses }}</b></span>
      </div>
      <div class="record-bar" role="img" :aria-label="summary">
        <span v-if="wins" class="record-segment record-wins" :style="{ flexGrow: wins }" :title="`Победы: ${wins}`"></span>
        <span v-if="losses" class="record-segment record-losses" :style="{ flexGrow: losses }" :title="`Поражения: ${losses}`"></span>
      </div>
    </template>
    <p v-else class="small muted">Боёв пока нет</p>
  </section>
</template>
