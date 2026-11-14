<script setup lang="ts">
import { ref, useId, watch } from 'vue'

/**
 * Раздел страницы, который сворачивается нажатием на заголовок. Свёрнутость
 * запоминается в браузере по ключу storageKey; без хранилища раздел просто открыт.
 */
const props = defineProps<{
  title: string
  storageKey: string
  /** Сколько записей внутри — число рядом с заголовком, видно и в свёрнутом виде. */
  count?: number
  /** Красный счётчик: записи ждут действия игрока. */
  attention?: boolean
}>()

const STORAGE_PREFIX = 'collapsed:'
const bodyId = useId()

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_PREFIX + props.storageKey) === '1'
  } catch {
    return false
  }
}

const collapsed = ref(readCollapsed())
watch(collapsed, (value) => {
  try {
    if (value) localStorage.setItem(STORAGE_PREFIX + props.storageKey, '1')
    else localStorage.removeItem(STORAGE_PREFIX + props.storageKey)
  } catch {
    // Без хранилища раздел свернётся только до перезагрузки страницы.
  }
})
</script>

<template>
  <section class="section">
    <h2 class="collapsible-head">
      <button type="button" :aria-expanded="!collapsed" :aria-controls="bodyId" @click="collapsed = !collapsed">
        <span class="collapsible-chevron" :class="{ closed: collapsed }" aria-hidden="true">▾</span>
        <span>{{ title }}</span>
        <span v-if="count !== undefined" class="section-count" :class="{ attention: attention && count > 0 }">{{ count }}</span>
      </button>
    </h2>
    <div v-show="!collapsed" :id="bodyId" class="section">
      <slot />
    </div>
  </section>
</template>
