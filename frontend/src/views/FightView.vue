<script setup lang="ts">
import { api } from '../api'
import FightExpanded from '../components/FightExpanded.vue'
import StateBlock from '../components/StateBlock.vue'
import { useLoad } from '../feedback'
import type { FightDetail } from '../types'

const props = defineProps<{ id: string }>()
const { data, error, loading, reload } = useLoad(() => api.get<FightDetail>(`/fights/${props.id}`))
</script>

<template>
  <main class="container page">
    <StateBlock :loading="loading" :error="error">
      <template v-if="data">
        <h1 class="sr-hidden">Бой #{{ data.id }}</h1>
        <FightExpanded :fight="data" @changed="reload" />
      </template>
    </StateBlock>
  </main>
</template>
