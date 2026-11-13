<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../../api'
import Modal from '../../components/Modal.vue'
import StateBlock from '../../components/StateBlock.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import { useAction, useLoad } from '../../feedback'
import { formatBoutDate, formatDateTime, methodLabel } from '../../format'
import type { OpenFightRow } from '../../types'

const list = useLoad(() => api.get<OpenFightRow[]>('/admin/fights/open'))
const { busy, run } = useAction()

const accepting = ref<OpenFightRow | null>(null)
const cancelling = ref<OpenFightRow | null>(null)
const reason = ref('')

function close(): void {
  accepting.value = null
  cancelling.value = null
  reason.value = ''
}

function winnerName(row: OpenFightRow): string {
  return row.winner_id === row.player1.id ? row.player1.nickname : row.player2.nickname
}

async function accept(): Promise<void> {
  const row = accepting.value
  if (!row) return
  const body = { reason: reason.value.trim() || null }
  if (await run(() => api.post(`/admin/fights/${row.id}/accept`, body), 'Бой засчитан')) {
    close()
    await list.reload()
  }
}

async function cancel(): Promise<void> {
  const row = cancelling.value
  if (!row) return
  if (await run(() => api.post(`/admin/fights/${row.id}/cancel`, { reason: reason.value }), 'Бой отменён')) {
    close()
    await list.reload()
  }
}
</script>

<template>
  <section class="section">
    <h2>Бои без итога</h2>
    <p class="small muted">
      Бои ждут подтверждения или исправления, самые ранние сверху. Зависший бой можно засчитать в текущей версии или отменить.
      Отменённый титульный или турнирный бой снова ждёт результата.
    </p>
    <StateBlock :loading="list.loading.value" :error="list.error.value" skeleton="list">
      <div v-if="list.data.value?.length" class="stack" style="gap: 12px">
        <article v-for="row in list.data.value" :key="row.id" class="card stack open-fight">
          <div class="row between">
            <RouterLink class="link" :to="`/fights/${row.id}`">
              <b>{{ row.player1.nickname }} — {{ row.player2.nickname }}</b>
            </RouterLink>
            <StatusBadge :fight="row.status" />
          </div>
          <p class="small">
            Бой #{{ row.id }} от {{ formatBoutDate(row.fought_at) }} · победа {{ winnerName(row) }}<template v-if="row.method">, {{ methodLabel[row.method] }}</template>.
            Записан {{ formatDateTime(row.created_at) }}.
          </p>
          <p class="small">
            Ждём: <b>{{ row.waiting_for.map((player) => player.nickname).join(', ') || '—' }}</b>
          </p>
          <p v-if="row.dispute_reason" class="small tone-red">Причина спора: {{ row.dispute_reason }}</p>
          <div class="row">
            <button class="btn sm primary" :disabled="busy" @click="accepting = row">Засчитать</button>
            <button class="btn sm danger" :disabled="busy" @click="cancelling = row">Отменить</button>
          </div>
        </article>
      </div>
      <p v-else class="empty">Все бои с итогом.</p>
    </StateBlock>
  </section>

  <Modal v-if="accepting" title="Засчитать бой" @close="close">
    <form class="stack" @submit.prevent="accept">
      <p class="small">
        {{ accepting.player1.nickname }} — {{ accepting.player2.nickname }}, {{ formatBoutDate(accepting.fought_at) }}.
        Победа {{ winnerName(accepting) }}. Очки начислятся сразу, как при подтверждении обоими игроками.
      </p>
      <label class="field">
        Комментарий (по желанию)
        <textarea v-model="reason" maxlength="500" placeholder="Например: соперник не отвечает неделю"></textarea>
      </label>
      <button class="btn primary" type="submit" :disabled="busy">Засчитать</button>
    </form>
  </Modal>

  <Modal v-if="cancelling" title="Отменить бой" @close="close">
    <form class="stack" @submit.prevent="cancel">
      <p class="small">
        {{ cancelling.player1.nickname }} — {{ cancelling.player2.nickname }}, {{ formatBoutDate(cancelling.fought_at) }}.
        Бой не попадёт в статистику и очки.
      </p>
      <label class="field">
        Причина
        <textarea v-model="reason" required minlength="3" maxlength="500" placeholder="Например: бой не состоялся"></textarea>
      </label>
      <button class="btn danger" type="submit" :disabled="busy">Отменить бой</button>
    </form>
  </Modal>
</template>
