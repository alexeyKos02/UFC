<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../../api'
import BeltIcon from '../../components/BeltIcon.vue'
import PlayerChip from '../../components/PlayerChip.vue'
import StateBlock from '../../components/StateBlock.vue'
import { useAction, useLoad } from '../../feedback'
import type { Belt } from '../../types'

const list = useLoad(() => api.get<Belt[]>('/belts'))
const { busy, run } = useAction()
const newName = ref('')
const names = reactive<Record<number, string>>({})

watch(list.data, (belts) => {
  for (const belt of belts ?? []) names[belt.id] = belt.name
})

async function create(): Promise<void> {
  if (await run(() => api.post('/admin/belts', { name: newName.value }), 'Пояс создан')) {
    newName.value = ''
    await list.reload()
  }
}

async function rename(belt: Belt): Promise<void> {
  await run(() => api.patch(`/admin/belts/${belt.id}`, { name: names[belt.id] }), 'Название обновлено')
  await list.reload()
}

async function uploadIcon(event: Event, belt: Belt): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await run(() => api.upload(`/admin/belts/${belt.id}/icon`, file), 'Иконка обновлена')
  input.value = ''
  await list.reload()
}
</script>

<template>
  <section class="card stack">
    <h3>Новый турнирный пояс</h3>
    <form class="row" style="flex-wrap: nowrap" @submit.prevent="create">
      <input v-model="newName" required maxlength="100" placeholder="Название пояса" aria-label="Название пояса" />
      <button class="btn primary" type="submit" :disabled="busy">Создать</button>
    </form>
  </section>
  <StateBlock :loading="list.loading.value" :error="list.error.value">
    <div class="grid">
      <article v-for="belt in list.data.value" :key="belt.id" class="card stack">
        <div class="row between">
          <div class="row">
            <BeltIcon :belt="belt" :size="48" />
            <RouterLink class="link" :to="`/belts/${belt.id}`">{{ belt.kind === 'main' ? 'Основной пояс' : 'Турнирный пояс' }}</RouterLink>
          </div>
          <PlayerChip v-if="belt.champion" :player="belt.champion" :size="24" />
          <span v-else class="small muted">Вакантен</span>
        </div>
        <form class="row" style="flex-wrap: nowrap" @submit.prevent="rename(belt)">
          <input v-model="names[belt.id]" required maxlength="100" aria-label="Название" />
          <button class="btn" type="submit" :disabled="busy">Сохранить</button>
        </form>
        <label class="field">
          Иконка (JPEG, PNG или WEBP)
          <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="busy" @change="uploadIcon($event, belt)" />
        </label>
      </article>
    </div>
  </StateBlock>
</template>
