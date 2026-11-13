import type { RatingHistoryPoint } from './types'

/** Что произошло с основным поясом в бою: значок над точкой графика и строка в легенде. */
export type BeltMark = 'take' | 'defend' | 'lose' | 'fail'

export function beltMark(item: RatingHistoryPoint): BeltMark | null {
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
