import React, { useEffect, useState } from 'react';
import { fetchGames } from '../api/client';
import { Game } from '../types';
import { GameCard } from '../components/GameCard';

export const GamesPage: React.FC = () => {
  const [games, setGames] = useState<Game[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Sorting state
  const [searchQuery, setSearchQuery] = useState('');
  const [platform, setPlatform] = useState('');
  const [sortField, setSortField] = useState<'metascore' | 'userscore' | 'title' | 'created_at'>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  const loadGames = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetchGames({
        q: searchQuery.trim() || undefined,
        platform: platform || undefined,
        sort: sortField,
        order: sortOrder,
        limit: 50,
      });
      setGames(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error fetching games');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handler = setTimeout(() => {
      loadGames();
    }, 250);
    return () => clearTimeout(handler);
  }, [searchQuery, platform, sortField, sortOrder]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.85rem', fontWeight: 700 }}>Games</h1>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          {total} {total === 1 ? 'game' : 'games'} found
        </span>
      </div>

      {/* Controls: Search, Platform filter placeholder, Sort selector */}
      <div className="controls-bar">
        <div className="search-wrapper">
          <input
            type="text"
            className="search-input"
            placeholder="Search games by title..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Platform filter placeholder */}
        <div className="filter-group">
          <select
            className="select-control"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          >
            <option value="">All Platforms</option>
            <option value="pc">PC</option>
            <option value="playstation-5">PlayStation 5</option>
            <option value="xbox-series-x">Xbox Series X</option>
            <option value="nintendo-switch">Nintendo Switch</option>
            <option value="nintendo-switch-2">Nintendo Switch 2</option>
            <option value="playstation-4">PlayStation 4</option>
          </select>
        </div>

        {/* Sort selector */}
        <div className="filter-group">
          <select
            className="select-control"
            value={sortField}
            onChange={(e) => setSortField(e.target.value as any)}
          >
            <option value="created_at">Date Added</option>
            <option value="metascore">Metascore</option>
            <option value="userscore">User Score</option>
            <option value="title">Title</option>
          </select>

          <button
            className="order-btn"
            onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
            title={`Order: ${sortOrder.toUpperCase()}`}
          >
            {sortOrder === 'asc' ? '↑ Asc' : '↓ Desc'}
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading games collection...</p>
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div className="error-state">
          <h3>Failed to load games</h3>
          <p>{error}</p>
          <button
            className="order-btn"
            style={{ marginTop: '1rem' }}
            onClick={() => loadGames()}
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty list state */}
      {!loading && !error && games.length === 0 && (
        <div className="empty-state">
          <h3>No games found</h3>
          <p>
            {searchQuery || platform
              ? 'Try adjusting your search query or platform filter.'
              : 'The catalog is currently empty. Ingestion pipeline will populate games in subsequent stages.'}
          </p>
        </div>
      )}

      {/* Populated Games grid */}
      {!loading && !error && games.length > 0 && (
        <div className="games-grid">
          {games.map((game) => (
            <GameCard key={game.id} game={game} />
          ))}
        </div>
      )}
    </div>
  );
};
