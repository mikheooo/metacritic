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

export interface GameReviewSummary {
  id: number;
  game_id: number;
  review_type: 'critic' | 'user';
  summary: string;
  likes: string[];
  dislikes: string[];
  review_count_used: number;
  total_reviews_seen: number;
  input_fingerprint: string;
  provider: string;
  model: string;
  prompt_version: string;
  input_tokens: number | null;
  output_tokens: number | null;
  generated_at: string;
  updated_at: string;
}

export interface SimilarGameItem {
  id: number;
  title: string;
  cover_url: string | null;
  similarity_score: number;
  platforms: string[];
}

export interface GameDetail extends Game {
  reviews: Review[];
  review_summaries?: GameReviewSummary[];
  critic_summary_detail?: GameReviewSummary | null;
  user_summary_detail?: GameReviewSummary | null;
  critic_review_count?: number;
  user_review_count?: number;
  similar_games?: SimilarGameItem[];
  lets_play?: YouTubeLetsPlayDetail | null;
}

export interface YouTubeTranscriptDetail {
  language: string;
  is_generated: boolean;
  provider: string;
}

export interface YouTubeSummaryDetail {
  text: string;
  key_points: string[];
  provider: string;
  model: string;
  prompt_version: string;
}

export interface YouTubeLetsPlayDetail {
  youtube_video_id: string;
  title: string;
  channel_title: string | null;
  url: string;
  thumbnail_url: string | null;
  view_count: number | null;
  duration_seconds: number | null;
  status: string;
  selection_rank: number;
  selection_reason: string;
  transcript?: YouTubeTranscriptDetail | null;
  summary?: YouTubeSummaryDetail | null;
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

export type PipelineStage =
  | 'queued'
  | 'discovering'
  | 'ingesting'
  | 'reviews'
  | 'summarizing'
  | 'embedding'
  | 'youtube'
  | 'similarity'
  | 'completed'
  | 'partial'
  | 'failed';

export type CrawlRunStatus = 'pending' | 'running' | 'completed' | 'partial' | 'failed';

export interface CrawlRunEvent {
  id: number;
  crawl_run_id: number;
  event_type: string;
  stage: string;
  game_id: number | null;
  message: string;
  payload: Record<string, any> | null;
  created_at: string;
}

export interface CrawlRun {
  id: number;
  task_id: string | null;
  status: CrawlRunStatus;
  trigger_type: 'scheduled' | 'manual';
  target_count: number;
  discovered_count: number;
  processed_count: number;
  failed_count: number;
  reviews_processed_count: number;
  summaries_generated_count: number;
  embeddings_generated_count: number;
  youtube_processed_count?: number;
  current_stage: PipelineStage | null;
  current_game_id: number | null;
  current_game_title: string | null;
  started_at: string | null;
  heartbeat_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
  created_at: string;
  events?: CrawlRunEvent[];
}

export interface SchedulerStatus {
  enabled: boolean;
  timezone: string;
  next_run_at: string | null;
  last_run_at: string | null;
}

export interface WorkerStatus {
  online: boolean;
  workers: string[];
}

export interface MonitorStatus {
  scheduler: SchedulerStatus;
  worker: WorkerStatus;
  active_run: CrawlRun | null;
  last_run: CrawlRun | null;
}

export interface PlatformItem {
  name: string;
  slug: string;
}

export interface RunNowResponse {
  run_id: number;
  task_id: string | null;
  status: string;
  trigger_type: string;
}

