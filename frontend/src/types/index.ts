export interface Platform {
  id: number;
  name: string;
  slug: string;
}

export interface GamePlatform {
  id: number;
  platform_id: number;
  platform: Platform;
  metascore: number | null;
  userscore: number | null;
}

export interface Review {
  id: number;
  review_type: 'critic' | 'user';
  external_id: string | null;
  author: string | null;
  rating: number | null;
  body: string | null;
  published_at: string | null;
  created_at: string;
}

export interface Game {
  id: number;
  title: string;
  metacritic_slug: string;
  metacritic_url: string;
  cover_url: string | null;
  developer: string | null;
  description: string | null;
  trailer_url: string | null;
  critic_summary: string | null;
  user_summary: string | null;
  created_at: string;
  updated_at: string;
  game_platforms: GamePlatform[];
}

export interface GameDetail extends Game {
  reviews: Review[];
}

export interface GameListResponse {
  items: Game[];
  total: number;
  limit: number;
  offset: number;
}

export interface HealthStatus {
  status: string;
  version: string;
}

export interface ReadyStatus {
  status: string;
  database: string;
  error?: string | null;
}
