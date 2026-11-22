import type { RatingHistoryPoint } from './types'

/** Что произошло с основным поясом в бою: значок над точкой графика и строка в легенде. */
export type BeltMark = 'take' | 'defend' | 'lose' | 'fail'

export function beltMark(item: RatingHistoryPoint): BeltMark | null {
  // Пояс меняется только в бою; призы турниров и очки от админа отмечаются своими значками.
  if (item.event !== 'fight') return null
  if (!item.champion_before && item.champion_after) return 'take'
  if (item.champion_before && !item.champion_after) return 'lose'
  if (!item.main_title_fight) return null
  return item.champion_before ? 'defend' : 'fail'
}

export const BELT_MARK_LABELS: Record<BeltMark, string> = {
  take: 'взял пояс',
  defend: 'защитил пояс',
  lose: 'потерял пояс',
  fail: 'не взял пояс',
}

/** Порядок в легенде. */
export const BELT_MARK_ORDER: BeltMark[] = ['take', 'defend', 'lose', 'fail']

/** Значки в квадрате 16×16. Корона — та же, что была на графике раньше. */
export const CROWN_PATH = 'M1 11 L2.5 3 L6 7 L8 1 L10 7 L13.5 3 L15 11 Z M1.5 12.5 H14.5 V14.5 H1.5 Z'
export const SHIELD_PATH = 'M8 0.5 L15 3.5 V8 C15 12 11.5 14.5 8 16 C4.5 14.5 1 12 1 8 V3.5 Z'
export const SHIELD_CHECK_PATH = 'M4.8 8.2 L7 10.4 L11.3 5.6'
export const CROWN_SLASH_PATH = 'M1 15.5 L15 0.5'

/**
 * Неосновной пояс: серебряные корона и щит над точкой боя (основной — золотые).
 * Неудачная попытка взять его — серебряная пунктирная контурная корона.
 */
export function sideBeltMark(item: RatingHistoryPoint): BeltMark | null {
  return item.event === 'fight' ? (item.side_belt?.mark ?? null) : null
}

export const SIDE_BELT_MARK_LABELS: Record<BeltMark, string> = {
  take: 'взял пояс (не основной)',
  defend: 'защитил пояс (не основной)',
  lose: 'потерял пояс (не основной)',
  fail: 'не взял пояс (не основной)',
}

export const SIDE_BELT_TIP: Record<BeltMark, string> = {
  take: 'Взял пояс',
  defend: 'Защитил пояс',
  lose: 'Потерял пояс',
  fail: 'Не взял пояс',
}

/** Место в турнире, за которое начислен приз: кубок с цифрой над точкой графика. */
export type PrizePlace = 1 | 2 | 3

export function prizePlace(item: RatingHistoryPoint): PrizePlace | null {
  return item.event === 'prize' ? (item.tournament_place ?? null) : null
}

export const PRIZE_LABELS: Record<PrizePlace, string> = {
  1: '1-е место в турнире',
  2: '2-е место в турнире',
  3: '3-е место в турнире',
}

export const PRIZE_ORDER: PrizePlace[] = [1, 2, 3]

/** Кубок в квадрате 16×16: чаша с ручками, ножка и подставка. Цифра места — в чаше. */
export const CUP_BOWL_PATH = 'M3.5 1 H12.5 V5 C12.5 8 10.5 9.8 8 9.8 C5.5 9.8 3.5 8 3.5 5 Z'
export const CUP_HANDLES_PATH = 'M3.6 2.6 H1.6 V4.2 C1.6 5.8 2.6 6.9 4.2 7.1 M12.4 2.6 H14.4 V4.2 C14.4 5.8 13.4 6.9 11.8 7.1'
export const CUP_BASE_PATH = 'M7 9.6 H9 V12 H7 Z M4.5 12.4 H11.5 V15 H4.5 Z'
