import {
  CrawlRun,
  GameDetail,
  GameListResponse,
  HealthStatus,
  MonitorStatus,
  PlatformItem,
  ReadyStatus,
  RunNowResponse,
} from '../types';

const API_BASE = '/api';

export interface GameFilterParams {
  q?: string;
  platform?: string;
  sort?: 'metascore' | 'userscore' | 'title' | 'created_at';
  order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

export async function fetchGames(params: GameFilterParams = {}): Promise<GameListResponse> {
  const searchParams = new URLSearchParams();
  if (params.q) searchParams.set('q', params.q);
  if (params.platform) searchParams.set('platform', params.platform);
  if (params.sort) searchParams.set('sort', params.sort);
  if (params.order) searchParams.set('order', params.order);
  if (params.limit !== undefined) searchParams.set('limit', params.limit.toString());
  if (params.offset !== undefined) searchParams.set('offset', params.offset.toString());

  const query = searchParams.toString();
  const url = `${API_BASE}/games${query ? `?${query}` : ''}`;

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch games: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchGameById(id: number): Promise<GameDetail> {
  const res = await fetch(`${API_BASE}/games/${id}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch game #${id}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch('/health');
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchReady(): Promise<ReadyStatus> {
  const res = await fetch('/ready');
  return res.json();
}

export async function fetchPlatforms(): Promise<PlatformItem[]> {
  const res = await fetch(`${API_BASE}/platforms`);
  if (!res.ok) {
    throw new Error(`Failed to fetch platforms: ${res.status}`);
  }
  return res.json();
}

export async function fetchMonitorStatus(): Promise<MonitorStatus> {
  const res = await fetch(`${API_BASE}/monitor/status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch monitor status: ${res.status}`);
  }
  return res.json();
}

export async function fetchMonitorRuns(limit = 20, offset = 0): Promise<CrawlRun[]> {
  const res = await fetch(`${API_BASE}/monitor/runs?limit=${limit}&offset=${offset}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch monitor runs: ${res.status}`);
  }
  return res.json();
}

export async function fetchMonitorRun(runId: number): Promise<CrawlRun> {
  const res = await fetch(`${API_BASE}/monitor/runs/${runId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch monitor run #${runId}: ${res.status}`);
  }
  return res.json();
}

export async function triggerRunNow(): Promise<RunNowResponse> {
  const res = await fetch(`${API_BASE}/crawler/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });

  if (res.status === 409) {
    const data = await res.json().catch(() => ({}));
    const err = new Error(data.detail || 'A Metacritic processing run is already active');
    (err as any).status = 409;
    (err as any).active_run_id = data.active_run_id;
    throw err;
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to trigger crawl run: ${res.status}`);
  }

  return res.json();
}

