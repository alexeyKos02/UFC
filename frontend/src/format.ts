import type {
  FightKind,
  FightMethod,
  FightStatus,
  MatchState,
  PromoType,
  RatingTier,
  Role,
  TitleFightStatus,
  TournamentCard,
  TournamentStatus,
} from './types'

export const tierLabel: Record<RatingTier, string> = {
  top: 'Топ',
  middle: 'Ни бе ни ме',
  bottom: 'Играть научись',
  calibration: 'Калибровка',
}

/** Сколько боёв нужно сыграть, чтобы выйти из калибровки (как CALIBRATION_FIGHTS на бэкенде). */
export const CALIBRATION_FIGHTS = 5

/** Сколько очков рекомендуем за победу в турнире: по 10 за каждый круг сетки. */
/**
 * Подсказка призов турнира в очки лиги. Бои турнира очков лиги не дают, поэтому приз заметный:
 * 25 очков за каждый круг сетки за 1-е место, 40% от него за 2-е, за 3-е — 20% (матч за 3-е место)
 * или 15% каждому из двух проигравших полуфиналистов.
 */
export function recommendedTournamentPrizes(capacity: number, hasThirdPlace: boolean): { first: number; second: number; third: number } {
  const rounds = Math.max(1, Math.ceil(Math.log2(Math.max(2, capacity))))
  const first = rounds * 25
  const third = rounds < 2 ? 0 : Math.round(first * (hasThirdPlace ? 0.2 : 0.15))
  return { first, second: Math.round(first * 0.4), third }
}

export const fightStatusLabel: Record<FightStatus, string> = {
  pending: 'Ждёт подтверждения',
  disputed: 'Оспорен',
  confirmed: 'Подтверждён',
  cancelled: 'Отменён',
  deleted: 'Удалён',
}

export const boutCaption: Record<FightKind, string> = {
  regular: 'Обычный бой',
  tournament: 'Турнирный бой',
  title: 'Титульный бой',
}

export const methodLabel: Record<FightMethod, string> = {
  ko_tko: 'KO/TKO',
  submission: 'Сабмишен',
  decision: 'Решение',
}

export const tournamentStatusLabel: Record<TournamentStatus, string> = {
  draft: 'Черновик',
  registration: 'Регистрация открыта',
  in_progress: 'Идёт',
  finished: 'Завершён',
  cancelled: 'Отменён',
}

export const matchStateLabel: Record<MatchState, string> = {
  bye: 'Проход без соперника',
  completed: 'Завершён',
  ready: 'Ждёт результата',
  waiting_players: 'Ждёт соперников',
  pending: 'Ждёт подтверждения',
  disputed: 'Оспорен',
  confirmed: 'Завершён',
  cancelled: 'Отменён',
  deleted: 'Удалён',
}

export const titleStatusLabel: Record<TitleFightStatus, string> = {
  scheduled: 'Назначен',
  completed: 'Завершён',
  cancelled: 'Отменён',
}

export const promoTypeLabel: Record<PromoType, string> = {
  tournament: 'Турнир',
  fight_announcement: 'Анонс боя',
  fighter_of_week: 'Боец недели',
}

export const roleLabel: Record<Role, string> = {
  player: 'Игрок',
  admin: 'Админ',
  owner: 'Владелец',
}

const dateTime = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})
const dateOnly = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })

export function formatDateTime(value: string | null): string {
  return value ? dateTime.format(new Date(value)) : '—'
}

const numericDateTime = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** Короткая дата для заглавных подписей в карточке боя. */
export function formatBoutDate(value: string): string {
  return numericDateTime.format(new Date(value))
}

const shortDate = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit' })

/** «13.11» — подписи на осях графиков. */
export function formatShortDate(value: string): string {
  return shortDate.format(new Date(value))
}

export function formatDate(value: string | null): string {
  return value ? dateOnly.format(new Date(value)) : '—'
}

/** Значение для input[type=datetime-local] в часовом поясе браузера. */
export function toLocalInput(value: string | Date): string {
  const date = new Date(value)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function fromLocalInput(value: string): string {
  return new Date(value).toISOString()
}

/** Форма слова для числа: plural(5, ['очко', 'очка', 'очков']) → 'очков'. */
export function plural(value: number, forms: [string, string, string]): string {
  const n = Math.abs(value) % 100
  const last = n % 10
  if (n > 10 && n < 20) return forms[2]
  if (last === 1) return forms[0]
  if (last >= 2 && last <= 4) return forms[1]
  return forms[2]
}

export function signed(value: number): string {
  if (value > 0) return `+${value}`
  return value < 0 ? `−${Math.abs(value)}` : '0'
}

export function resultLine(method: FightMethod | null, round: number | null): string {
  const parts: string[] = []
  if (method) parts.push(methodLabel[method])
  if (round) parts.push(`${round} раунд`)
  return parts.join(', ')
}

export function seatsLine(tournament: TournamentCard): string {
  return `${tournament.seats_taken} из ${tournament.capacity}`
}

export function isFull(tournament: TournamentCard): boolean {
  return tournament.seats_taken >= tournament.capacity
}

export function tournamentCta(tournament: TournamentCard): string {
  switch (tournament.status) {
    case 'registration':
      if (tournament.is_participant) return 'Вы участвуете'
      return isFull(tournament) ? 'Мест нет' : 'Вступить'
    case 'in_progress':
      return 'Смотреть сетку'
    case 'finished':
      return 'Итоги турнира'
    case 'cancelled':
      return 'Турнир отменён'
    default:
      return 'Подробнее'
  }
}

/** crypto.randomUUID есть только на HTTPS и localhost, а лига может работать по обычному HTTP. */
export function requestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
