<script setup lang="ts">
import { computed } from 'vue'
import AnimatedNumber from './AnimatedNumber.vue'

const props = defineProps<{ wins: number; losses: number; winRate: number | null }>()

const fights = computed(() => props.wins + props.losses)
const summary = computed(
  () => `Победы: ${props.wins}, поражения: ${props.losses}, процент побед: ${props.winRate ?? 0}%`,
)
</script>

<template>
  <section class="record" aria-label="Статистика боёв">
    <template v-if="fights">
      <!-- При смене значений (например, «Все бои / Лига / Турниры» в профиле) числа сменяются
           с переходом, а доли полосы плавно перетекают. -->
      <div class="record-labels" aria-hidden="true">
        <span class="record-label"><i class="record-swatch record-wins"></i>Победы <b><AnimatedNumber :value="wins" /></b></span>
        <span>Боёв <b><AnimatedNumber :value="fights" /></b> · Побед <b><AnimatedNumber :value="winRate ?? 0" />%</b></span>
        <span class="record-label"><i class="record-swatch record-losses"></i>Поражения <b><AnimatedNumber :value="losses" /></b></span>
      </div>
      <div class="record-bar" role="img" :aria-label="summary">
        <span class="record-segment record-wins" :class="{ zero: !wins }" :style="{ flexGrow: wins }" :title="`Победы: ${wins}`"></span>
        <span class="record-segment record-losses" :class="{ zero: !losses }" :style="{ flexGrow: losses }" :title="`Поражения: ${losses}`"></span>
      </div>
    </template>
    <p v-else class="small muted">Боёв пока нет</p>
  </section>
</template>
