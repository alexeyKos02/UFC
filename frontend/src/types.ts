export type Role = 'player' | 'admin' | 'owner'
export type RatingTier = 'top' | 'middle' | 'bottom'
export type FightStatus = 'pending' | 'disputed' | 'confirmed' | 'cancelled'
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
  points_after: number
  place_after: number
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
  win_points: number
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
  player: PlayerBrief
  points: number
  points_place: number | null
  display_place: number | null
  is_special: boolean
  is_champion: boolean
  fights: number
  wins: number
  losses: number
  win_rate: number | null
}

export interface RivalStat {
  player: PlayerBrief
  count: number
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
  }
  stats: {
    fights: number
    wins: number
    losses: number
    win_rate: number | null
    best_streak: number
    nemeses: RivalStat[]
    victims: RivalStat[]
  }
  belts: { active: ProfileBelt[]; past: ProfileBelt[] }
  is_me: boolean
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
