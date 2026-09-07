import { GameDetail, GameListResponse, HealthStatus, ReadyStatus } from '../types';

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
