export type Role = 'player' | 'admin' | 'owner'
export type RatingTier = 'top' | 'middle' | 'bottom' | 'calibration'
export type FightStatus = 'pending' | 'disputed' | 'confirmed' | 'cancelled' | 'deleted'
export type FightKind = 'regular' | 'tournament' | 'title'
export type FightMethod = 'ko_tko' | 'submission' | 'decision'
export type TournamentStatus = 'draft' | 'registration' | 'in_progress' | 'finished' | 'cancelled'
export type TitleFightStatus = 'scheduled' | 'completed' | 'cancelled'
export type PromoType = 'tournament' | 'fight_announcement' | 'fighter_of_week'
export type MatchState = 'bye' | 'completed' | 'ready' | 'waiting_players' | FightStatus

export interface Account {
  id: number
  login: string
  nickname: string
  role: Role
  status: 'active' | 'blocked'
  avatar_url: string | null
  full_body_url: string | null
  rating_points: number
  /** Прошёл или пропустил знакомство с сайтом. */
  onboarded: boolean
}

export interface AdminUser extends Account {
  created_at: string
  special_place: number | null
}

export interface PlayerBrief {
  id: number
  nickname: string
  avatar_url: string | null
  status: string
}

export interface Fighter extends PlayerBrief {
  full_body_url: string | null
}

export interface BeltBrief {
  id: number
  name: string
  kind: 'main' | 'tournament'
  icon_url: string | null
}

export interface Belt extends BeltBrief {
  champion: PlayerBrief | null
}

export interface LinkRef {
  id: number
  title: string
}

export interface BeltWin {
  id: number
  won_at: string
  player: PlayerBrief
  is_defense: boolean
  /** null — пояс выдан админом или владельцем без боя. */
  fight_id: number | null
  tournament: LinkRef | null
  title_fight_id: number | null
}

export interface BeltDetail extends Belt {
  history: BeltWin[]
}

export interface ProfileBelt {
  belt: BeltBrief
  caption: string
  wins: BeltWin[]
}

export interface Votes {
  first: number
  second: number
  my_vote: number | null
}

export interface UpcomingBout {
  kind: 'planned' | 'title' | 'tournament'
  id: number
  player1: Fighter
  player2: Fighter
  scheduled_at: string | null
  tournament: LinkRef | null
  round_name: string | null
  votes: Votes
  can_vote: boolean
  can_submit: boolean
  can_cancel: boolean
}

export interface FightBrief {
  id: number
  kind: FightKind
  status: FightStatus
  version_no: number
  player1: Fighter
  player2: Fighter
  initiator_id: number
  fought_at: string
  winner_id: number
  method: FightMethod | null
  round: number | null
  confirmed_at: string | null
  points_change: [number, number] | null
  votes: Votes | null
  tournament: LinkRef | null
  title_fight_id: number | null
  can_confirm: boolean
  can_dispute: boolean
  can_correct: boolean
  dispute_reason: string | null
  /** Подтверждённый бой удалён админом: очки, пояс и сетка откатились. */
  deletion: FightDeletion | null
}

export interface FightDeletion {
  by: PlayerBrief | null
  reason: string | null
  at: string
}

/** Найденные в админке бои: страница результатов и сколько всего подходит. */
export interface FightSearchPage {
  items: FightBrief[]
  total: number
  page_size: number
}

/** Решение админа по зависшему бою. */
export interface FightResolution {
  by: PlayerBrief
  reason: string | null
  at: string
  accepted: boolean
}

export interface OpenFightRow extends FightBrief {
  created_at: string
  waiting_for: PlayerBrief[]
}

export interface FightVersion {
  version_no: number
  submitted_by: PlayerBrief
  fought_at: string
  winner: PlayerBrief
  method: FightMethod | null
  round: number | null
  dispute_reason: string | null
  disputed_by: PlayerBrief | null
  disputed_at: string | null
  created_at: string
  confirmed_by: PlayerBrief[]
}

export interface RatingChange {
  player: PlayerBrief
  place_before: number
  points_before: number
  delta: number
  /** Только у проигравшего: на сколько меньше он потерял благодаря скидке за активность. */
  loss_discount: number
  points_after: number
  place_after: number
  /** Номер в таблице рейтинга до и после боя. У чемпиона номера нет: null и champion_* = true. */
  table_place_before: number | null
  table_place_after: number | null
  champion_before: boolean
  champion_after: boolean
}

export interface FightAdjustment {
  winner_delta: number
  loser_delta: number
  reason: string
  version: number
}

export interface FightDetail extends FightBrief {
  versions: FightVersion[]
  rating_changes: RatingChange[]
  adjustment: FightAdjustment | null
  is_title_defense: boolean | null
  resolution: FightResolution | null
  /** Очки пересчитаны: позже подтвердили бой, сыгранный раньше этого. */
  recalculated: { at: string; because_fight_id: number | null } | null
  comparison?: {
    head_to_head: [number, number]
    league_wins: [number, number]
    league_losses: [number, number]
  }
}

export interface ResultPayload {
  fought_at: string
  winner_id: number
  method: FightMethod | null
  round: number | null
}

export interface TournamentCard {
  id: number
  title: string
  description: string
  status: TournamentStatus
  capacity: number
  /** Призы в очки лиги за 1-е, 2-е и 3-е место. */
  win_points: number
  second_points: number
  third_points: number
  has_third_place: boolean
  seats_taken: number
  belt: BeltBrief
  winner: PlayerBrief | null
  is_participant: boolean
  cancel_reason: string | null
  started_at: string | null
  finished_at: string | null
}

export interface MatchOut {
  id: number
  round: number
  position: number
  player1: PlayerBrief | null
  player2: PlayerBrief | null
  winner_id: number | null
  is_bye: boolean
  is_third_place: boolean
  state: MatchState
  fight_id: number | null
  can_submit: boolean
  tournament: LinkRef
  round_name: string
}

export interface RoundOut {
  round: number
  name: string
  matches: MatchOut[]
}

export interface TournamentDetail extends TournamentCard {
  participants: PlayerBrief[]
  rounds: RoundOut[]
}

export interface TitleFight {
  id: number
  belt: BeltBrief
  player1: PlayerBrief
  player2: PlayerBrief
  champion_id: number | null
  scheduled_at: string | null
  status: TitleFightStatus
  winner: PlayerBrief | null
  is_defense: boolean | null
  cancel_reason: string | null
  created_at: string
  fight: FightBrief | null
  can_submit: boolean
}

export interface Promo {
  id: number
  type: PromoType
  title: string
  description: string
  image_url: string | null
  tournament: TournamentCard | null
  fighter1: PlayerBrief | null
  fighter2: PlayerBrief | null
  fight_at: string | null
  player: PlayerBrief | null
  is_published: boolean
  show_from: string | null
  show_until: string | null
  sort_order: number
}

export interface HomeData {
  /** Назначенные титульные бои без результата: за них голосуют прямо на главной. */
  title_fights: UpcomingBout[]
  tournaments: TournamentCard[]
  promos: Promo[]
}

export interface MyFights {
  to_confirm: FightBrief[]
  waiting: FightBrief[]
  disputed: FightBrief[]
  matches: MatchOut[]
  upcoming: UpcomingBout[]
}

export interface LeagueRow {
  /** У чемпиона дополнительно приходит фото в полный рост. */
  player: PlayerBrief & { full_body_url?: string | null }
  /** Только у чемпиона: основной пояс. */
  belt?: BeltBrief
  points: number
  points_place: number | null
  display_place: number | null
  is_special: boolean
  is_champion: boolean
  /** Меньше 5 боёв: игрок стоит ниже всех откалиброванных. */
  is_calibrating: boolean
  fights: number
  wins: number
  losses: number
  win_rate: number | null
}

export interface RivalStat {
  player: PlayerBrief
  count: number
}

export type StatScope = 'all' | 'league' | 'tournament'

export interface PlayerStats {
  fights: number
  wins: number
  losses: number
  win_rate: number | null
  best_streak: number
  nemeses: RivalStat[]
  victims: RivalStat[]
}

export interface PlayerProfile {
  player: PlayerBrief & { full_body_url: string | null; created_at: string }
  rating: {
    points: number
    display_place: number | null
    points_place: number | null
    is_special: boolean
    is_champion: boolean
    tier: RatingTier | null
    is_calibrating: boolean
    /** Неделя и больше без боёв: сколько дней и сколько очков уже снято за этот простой. */
    inactivity: { days_without_fights: number; lost_points: number; decay_starts_at: string } | null
  }
  /** Общая статистика и отдельно бои лиги (обычные и титульные) и турниров. */
  stats: Record<StatScope, PlayerStats>
  belts: { active: ProfileBelt[]; past: ProfileBelt[] }
  is_me: boolean
  /** Очные встречи зрителя с этим игроком; на своей странице null. */
  head_to_head: HeadToHead | null
}

export type MethodKey = FightMethod | 'none'

export interface HeadToHead {
  fights: number
  my_wins: number
  their_wins: number
  methods: { mine: Partial<Record<MethodKey, number>>; theirs: Partial<Record<MethodKey, number>> }
  /** Текущая серия побед подряд в очных встречах: чья и сколько. */
  streak: { mine: boolean; count: number } | null
  /** Сколько очков рейтинга зритель выиграл (плюс) или отдал (минус) в этих боях. */
  points: number
  recent: {
    fight_id: number
    fought_at: string
    won: boolean
    method: FightMethod | null
    round: number | null
    kind: FightKind
  }[]
}

export interface AdminRatingRow {
  player: PlayerBrief
  points: number
  points_place: number
  display_place: number | null
  is_special: boolean
  is_champion: boolean
}

export interface AdminRating {
  rows: AdminRatingRow[]
  active_count: number
  special_places: { place: number; player: PlayerBrief; updated_at: string }[]
}

export interface UpsetRow {
  fight_id: number
  fought_at: string
  kind: FightKind
  winner: PlayerBrief
  loser: PlayerBrief
  winner_place_before: number
  loser_place_before: number
  auto_delta: number
  adjustment: { winner_delta: number; reason: string | null; status: string; version: number } | null
}

export interface AdjustmentLogRow {
  id: number
  fight_id: number
  action: 'create' | 'update' | 'cancel'
  actor: PlayerBrief
  reason: string
  winner: PlayerBrief
  loser: PlayerBrief
  winner_delta_before: number
  winner_delta_after: number
  winner_points_before: number
  winner_points_after: number
  loser_points_before: number
  loser_points_after: number
  created_at: string
}

export interface SpecialPlaceLogRow {
  id: number
  player: PlayerBrief
  action: 'set' | 'change' | 'clear'
  place_before: number | null
  place_after: number | null
  actor: PlayerBrief
  created_at: string
}

/** Вид заготовки, которую показывает StateBlock во время загрузки. */
export type SkeletonKind = 'table' | 'league' | 'cards' | 'list' | 'profile' | 'fight' | 'form'

/** Точка истории игрока: очки и номер в таблице после одного боя. */
export interface RatingHistoryPoint {
  fight_id: number
  kind: FightKind
  fought_at: string
  confirmed_at: string
  won: boolean
  opponent: PlayerBrief
  delta: number
  points_before: number
  points_after: number
  /** Номер в таблице; у чемпиона null и champion_* = true. */
  table_place_before: number | null
  table_place_after: number | null
  champion_before: boolean
  champion_after: boolean
  /** Титульный бой за основной пояс: по нему отмечаются защиты и неудачные попытки. */
  main_title_fight: boolean
}
