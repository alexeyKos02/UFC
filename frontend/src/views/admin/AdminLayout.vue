<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { isOwner } from '../../auth'
</script>

<template>
  <main class="container page">
    <h1>Админка</h1>
    <nav class="admin-tabs" aria-label="Разделы админки">
      <RouterLink to="/admin/tournaments">Турниры</RouterLink>
      <RouterLink to="/admin/belts">Пояса</RouterLink>
      <RouterLink to="/admin/title-fights">Титульные бои</RouterLink>
      <RouterLink to="/admin/fights">Бои без итога</RouterLink>
      <RouterLink to="/admin/rating">Рейтинг</RouterLink>
      <RouterLink to="/admin/promos">Промоплашки</RouterLink>
      <RouterLink v-if="isOwner" to="/admin/users">Роли и блокировки</RouterLink>
    </nav>
    <RouterView />
  </main>
</template>
