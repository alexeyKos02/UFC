<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { api } from '../api'
import PromoCard from '../components/PromoCard.vue'
import StateBlock from '../components/StateBlock.vue'
import TournamentTile from '../components/TournamentTile.vue'
import UpcomingBoutCard from '../components/UpcomingBoutCard.vue'
import { useLoad } from '../feedback'
import type { HomeData } from '../types'

const { data, error, loading, reload } = useLoad(() => api.get<HomeData>('/home'))
</script>

<template>
  <main class="container page">
    <div class="page-head">
      <h1>Главная</h1>
      <RouterLink class="btn primary" to="/fights/new">Записать бой</RouterLink>
    </div>
    <StateBlock :loading="loading" :error="error" skeleton="cards">
      <template v-if="data">
        <section v-if="data.title_fights.length" class="section">
          <h2>{{ data.title_fights.length > 1 ? 'Титульные бои' : 'Титульный бой' }}</h2>
          <div class="stack" style="gap: 16px">
            <UpcomingBoutCard v-for="bout in data.title_fights" :key="bout.id" :bout="bout" @changed="reload" />
          </div>
        </section>
        <section v-if="data.promos.length" class="section" aria-label="Промо">
          <div class="grid">
            <PromoCard v-for="promo in data.promos" :key="promo.id" :promo="promo" />
          </div>
        </section>
        <section class="section">
          <div class="section-head">
            <h2>Турниры</h2>
            <RouterLink class="link small" to="/tournaments">Все турниры</RouterLink>
          </div>
          <div v-if="data.tournaments.length" class="grid">
            <TournamentTile v-for="item in data.tournaments" :key="item.id" :tournament="item" @changed="reload" />
          </div>
          <p v-else class="empty">Сейчас нет турниров с открытой регистрацией или идущих боёв.</p>
        </section>
      </template>
    </StateBlock>
  </main>
</template>
