import React, { useEffect, useState } from 'react';
import { fetchGames, fetchPlatforms } from '../api/client';
import { Game, PlatformItem } from '../types';
import { GameCard } from '../components/GameCard';

export const GamesPage: React.FC = () => {
  const [games, setGames] = useState<Game[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Available dynamic platforms from database
  const [availablePlatforms, setAvailablePlatforms] = useState<PlatformItem[]>([]);

  // Filters & Sorting state
  const [searchQuery, setSearchQuery] = useState('');
  const [platform, setPlatform] = useState('');
  const [sortField, setSortField] = useState<'metascore' | 'userscore' | 'title' | 'created_at'>('metascore');
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
    fetchPlatforms()
      .then((data) => setAvailablePlatforms(data))
      .catch((err) => console.warn('Failed to fetch platforms:', err));
  }, []);

  useEffect(() => {
    const handler = setTimeout(() => {
      loadGames();
    }, 250);
    return () => clearTimeout(handler);
  }, [searchQuery, platform, sortField, sortOrder]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.85rem', fontWeight: 700 }}>Каталог игр</h1>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          Найдено: {total}
        </span>
      </div>

      {/* Controls: Search, Platform filter placeholder, Sort selector */}
      <div className="controls-bar">
        <div className="search-wrapper">
          <input
            type="text"
            className="search-input"
            placeholder="Поиск игр по названию..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Dynamic Platform filter */}
        <div className="filter-group">
          <select
            className="select-control"
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
          >
            <option value="">Все платформы</option>
            {availablePlatforms.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* Sort selector */}
        <div className="filter-group">
          <select
            className="select-control"
            value={sortField}
            onChange={(e) => setSortField(e.target.value as any)}
          >
            <option value="metascore">По рейтингу Metascore</option>
            <option value="userscore">По оценке игроков</option>
            <option value="created_at">По дате добавления</option>
            <option value="title">По названию (А-Я)</option>
          </select>

          <button
            className="order-btn"
            onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
            title={sortOrder === 'asc' ? 'Сортировка: По возрастанию' : 'Сортировка: По убыванию'}
            style={{ whiteSpace: 'nowrap' }}
          >
            {sortOrder === 'asc' ? '↑ По возрастанию' : '↓ По убыванию'}
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Загрузка каталога игр...</p>
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div className="error-state">
          <h3>Не удалось загрузить каталог</h3>
          <p>{error}</p>
          <button
            className="order-btn"
            style={{ marginTop: '1rem' }}
            onClick={() => loadGames()}
          >
            Повторить
          </button>
        </div>
      )}

      {/* Empty list state */}
      {!loading && !error && games.length === 0 && (
        <div className="empty-state">
          <h3>Игры не найдены</h3>
          <p>
            {searchQuery || platform
              ? 'Попробуйте изменить поисковый запрос или фильтр платформы.'
              : 'Каталог пока пуст. Игры загружаются фоновым роботом.'}
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
