<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { currentUser } from '../auth'
import BeltIcon from '../components/BeltIcon.vue'
import FightCard from '../components/FightCard.vue'
import PlayerChip from '../components/PlayerChip.vue'
import ResultSubmit from '../components/ResultSubmit.vue'
import StateBlock from '../components/StateBlock.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useLoad } from '../feedback'
import { formatDateTime } from '../format'
import type { MyFights } from '../types'

const { data, error, loading, reload } = useLoad(() => api.get<MyFights>('/fights/mine'))
</script>

<template>
  <main class="container page">
    <div class="page-head">
      <h1>Мои бои</h1>
      <div class="row">
        <RouterLink class="btn" :to="`/players/${currentUser?.id}`">История в профиле</RouterLink>
        <RouterLink class="btn primary" to="/fights/new">Записать бой</RouterLink>
      </div>
    </div>
    <StateBlock :loading="loading" :error="error">
      <template v-if="data">
        <section class="section">
          <h2>На подтверждение</h2>
          <div v-if="data.to_confirm.length" class="grid">
            <FightCard v-for="fight in data.to_confirm" :key="fight.id" :fight="fight" actions @changed="reload" />
          </div>
          <p v-else class="empty">Нет результатов, которые ждут вашего решения.</p>
        </section>

        <section class="section">
          <h2>Бой за основной пояс</h2>
          <div v-if="data.title_fights.length" class="grid">
            <article v-for="item in data.title_fights" :key="item.id" class="card stack">
              <div class="row between">
                <div class="row">
                  <BeltIcon :belt="item.belt" :size="36" />
                  <b>{{ item.belt.name }}</b>
                </div>
                <StatusBadge :title="item.status" />
              </div>
              <div class="fight-row">
                <PlayerChip :player="item.player1" />
                <span class="versus">VS</span>
                <div class="right"><PlayerChip :player="item.player2" /></div>
              </div>
              <p class="small muted">Дата: {{ item.scheduled_at ? formatDateTime(item.scheduled_at) : 'не назначена' }}</p>
              <ResultSubmit v-if="item.can_submit" :url="`/title-fights/${item.id}/result`" :player1="item.player1" :player2="item.player2" @done="reload" />
              <RouterLink v-else-if="item.fight" class="link small" :to="`/fights/${item.fight.id}`">Открыть запись боя</RouterLink>
            </article>
          </div>
          <p v-else class="empty">Титульный бой вам не назначен.</p>
        </section>

        <section class="section">
          <h2>Матчи турниров</h2>
          <div v-if="data.matches.length" class="grid">
            <article v-for="match in data.matches" :key="match.id" class="card stack">
              <div class="row between">
                <RouterLink class="link" :to="`/tournaments/${match.tournament.id}`">{{ match.tournament.title }}</RouterLink>
                <StatusBadge :match="match.state" />
              </div>
              <p class="small muted">{{ match.round_name }}</p>
              <div class="fight-row">
                <PlayerChip v-if="match.player1" :player="match.player1" />
                <span v-else class="tbd small">Определится позже</span>
                <span class="versus">VS</span>
                <div class="right">
                  <PlayerChip v-if="match.player2" :player="match.player2" />
                  <span v-else class="tbd small">Определится позже</span>
                </div>
              </div>
              <ResultSubmit
                v-if="match.can_submit && match.player1 && match.player2"
                :url="`/tournaments/matches/${match.id}/result`"
                :player1="match.player1"
                :player2="match.player2"
                @done="reload"
              />
            </article>
          </div>
          <p v-else class="empty">Матчей, ожидающих результата, нет.</p>
        </section>

        <section class="section">
          <h2>Оспоренные</h2>
          <div v-if="data.disputed.length" class="grid">
            <FightCard v-for="fight in data.disputed" :key="fight.id" :fight="fight" actions @changed="reload" />
          </div>
          <p v-else class="empty">Оспоренных записей нет.</p>
        </section>

        <section class="section">
          <h2>Ждут подтверждения соперника</h2>
          <div v-if="data.waiting.length" class="grid">
            <FightCard v-for="fight in data.waiting" :key="fight.id" :fight="fight" />
          </div>
          <p v-else class="empty">Отправленных записей нет.</p>
        </section>
      </template>
    </StateBlock>
  </main>
</template>
