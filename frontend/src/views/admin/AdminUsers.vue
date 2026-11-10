<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../../api'
import { currentUser } from '../../auth'
import PlayerChip from '../../components/PlayerChip.vue'
import StateBlock from '../../components/StateBlock.vue'
import { useAction, useLoad } from '../../feedback'
import { roleLabel } from '../../format'
import type { AdminUser } from '../../types'

const list = useLoad(() => api.get<AdminUser[]>('/admin/users'))
const { busy, run } = useAction()
const search = ref('')

const rows = computed(() => {
  const query = search.value.trim().toLowerCase()
  return (list.data.value ?? []).filter(
    (user) => !query || user.nickname.toLowerCase().includes(query) || user.login.includes(query),
  )
})

function brief(user: AdminUser) {
  return { id: user.id, nickname: user.nickname, avatar_url: user.avatar_url, status: user.status }
}

function manageable(user: AdminUser): boolean {
  return user.role !== 'owner' && user.id !== currentUser.value?.id
}

async function setRole(user: AdminUser, role: string): Promise<void> {
  await run(() => api.post(`/admin/users/${user.id}/role`, { role }), 'Роль изменена')
  await list.reload()
}

async function toggleBlock(user: AdminUser): Promise<void> {
  const blocking = user.status === 'active'
  if (blocking && !window.confirm(`Заблокировать ${user.nickname}? Все его сессии будут завершены.`)) return
  const action = blocking ? 'block' : 'unblock'
  await run(() => api.post(`/admin/users/${user.id}/${action}`), blocking ? 'Заблокирован' : 'Разблокирован')
  await list.reload()
}
</script>

<template>
  <input v-model="search" type="search" placeholder="Поиск по нику или логину" aria-label="Поиск по нику или логину" style="max-width: 320px" />
  <StateBlock :loading="list.loading.value" :error="list.error.value">
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Игрок</th><th class="hide-sm">Логин</th><th>Роль</th><th>Статус</th><th>Действия</th></tr>
        </thead>
        <tbody>
          <tr v-for="user in rows" :key="user.id">
            <td><PlayerChip :player="brief(user)" :size="24" /></td>
            <td class="hide-sm small muted">{{ user.login }}</td>
            <td>
              <select v-if="manageable(user)" :value="user.role" :disabled="busy" style="width: auto" :aria-label="`Роль игрока ${user.nickname}`" @change="setRole(user, ($event.target as HTMLSelectElement).value)">
                <option value="player">Игрок</option>
                <option value="admin">Админ</option>
              </select>
              <span v-else class="small">{{ roleLabel[user.role] }}</span>
            </td>
            <td>
              <span class="badge" :class="user.status === 'active' ? 'tone-green' : 'tone-red'">{{ user.status === 'active' ? 'Активен' : 'Заблокирован' }}</span>
            </td>
            <td>
              <button v-if="manageable(user)" class="btn sm" :class="{ danger: user.status === 'active' }" :disabled="busy" @click="toggleBlock(user)">
                {{ user.status === 'active' ? 'Заблокировать' : 'Разблокировать' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </StateBlock>
</template>
