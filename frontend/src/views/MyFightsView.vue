<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { currentUser } from '../auth'
import CollapsibleSection from '../components/CollapsibleSection.vue'
import FightCard from '../components/FightCard.vue'
import PlayerChip from '../components/PlayerChip.vue'
import StateBlock from '../components/StateBlock.vue'
import StatusBadge from '../components/StatusBadge.vue'
import UpcomingBoutCard from '../components/UpcomingBoutCard.vue'
import { useLoad } from '../feedback'
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
    <StateBlock :loading="loading" :error="error" skeleton="list">
      <template v-if="data">
        <CollapsibleSection
          title="На подтверждение"
          storage-key="my-fights:to-confirm"
          :count="data.to_confirm.length"
          attention
          data-tour="to-confirm"
        >
          <p v-if="data.to_confirm.length > 1" class="small muted">Сверху — более ранние бои.</p>
          <div v-if="data.to_confirm.length" class="stack" style="gap: 16px">
            <FightCard v-for="fight in data.to_confirm" :key="fight.id" :fight="fight" actions @changed="reload" />
          </div>
          <p v-else class="empty">Нет результатов, которые ждут вашего решения.</p>
        </CollapsibleSection>

        <CollapsibleSection title="Предстоящие бои" storage-key="my-fights:upcoming" :count="data.upcoming.length">
          <div v-if="data.upcoming.length" class="stack" style="gap: 16px">
            <UpcomingBoutCard v-for="bout in data.upcoming" :key="`${bout.kind}-${bout.id}`" :bout="bout" @changed="reload" />
          </div>
          <p v-else class="empty">Предстоящих боёв нет.</p>
        </CollapsibleSection>

        <CollapsibleSection
          v-if="data.matches.length"
          title="Турниры: соперник ещё не определён"
          storage-key="my-fights:matches"
          :count="data.matches.length"
        >
          <div class="grid">
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
            </article>
          </div>
        </CollapsibleSection>

        <CollapsibleSection title="Оспоренные" storage-key="my-fights:disputed" :count="data.disputed.length">
          <div v-if="data.disputed.length" class="stack" style="gap: 16px">
            <FightCard v-for="fight in data.disputed" :key="fight.id" :fight="fight" actions @changed="reload" />
          </div>
          <p v-else class="empty">Оспоренных записей нет.</p>
        </CollapsibleSection>

        <CollapsibleSection
          title="Ждут подтверждения соперника"
          storage-key="my-fights:waiting"
          :count="data.waiting.length"
          data-tour="waiting"
        >
          <div v-if="data.waiting.length" class="stack" style="gap: 16px">
            <FightCard v-for="fight in data.waiting" :key="fight.id" :fight="fight" />
          </div>
          <p v-else class="empty">Отправленных записей нет.</p>
        </CollapsibleSection>
      </template>
    </StateBlock>
  </main>
</template>
