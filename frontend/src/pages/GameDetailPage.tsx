import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchGameById } from '../api/client';
import { GameDetail } from '../types';
import { ScoreBadge } from '../components/ScoreBadge';

export const GameDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [game, setGame] = useState<GameDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    const gameId = parseInt(id, 10);
    if (isNaN(gameId)) {
      setError('Invalid Game ID');
      setLoading(false);
      return;
    }

    fetchGameById(gameId)
      .then((data) => {
        setGame(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Error loading game');
        setLoading(false);
      });
  }, [id]);

  if (loading) {
    return (
      <div className="loading-state">
        <div className="spinner"></div>
        <p>Loading game details...</p>
      </div>
    );
  }

  if (error || !game) {
    return (
      <div className="error-state">
        <h3>Game not found</h3>
        <p>{error || 'The requested game could not be found.'}</p>
        <Link to="/" className="back-btn" style={{ marginTop: '1.5rem', display: 'inline-flex' }}>
          ← Back to Catalog
        </Link>
      </div>
    );
  }

  return (
    <div className="detail-page">
      <Link to="/" className="back-btn">
        ← Back to Catalog
      </Link>

      <div className="detail-header">
        {game.cover_url ? (
          <img src={game.cover_url} alt={game.title} className="detail-cover" />
        ) : (
          <div className="detail-cover" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
            No Cover Available
          </div>
        )}

        <div className="detail-info">
          <h1 className="detail-title">{game.title}</h1>
          <p className="detail-meta">
            Developed by <strong>{game.developer || 'Unknown'}</strong> • Added {new Date(game.created_at).toLocaleDateString()}
          </p>

          <div style={{ marginBottom: '1.5rem' }}>
            <h4 style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
              Platforms & Scores
            </h4>
            {game.game_platforms.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>No platform scores registered yet.</p>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
                {game.game_platforms.map((gp) => (
                  <div
                    key={gp.id}
                    style={{
                      backgroundColor: 'rgba(255,255,255,0.03)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '8px',
                      padding: '0.75rem 1rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '1rem',
                    }}
                  >
                    <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>{gp.platform.name}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Meta:</span>
                      <ScoreBadge score={gp.metascore} type="metascore" />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>User:</span>
                      <ScoreBadge score={gp.userscore} type="userscore" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {game.metacritic_url && (
            <a
              href={game.metacritic_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: 'var(--accent-primary)',
                fontSize: '0.9rem',
                textDecoration: 'underline',
              }}
            >
              View on Metacritic ↗
            </a>
          )}
        </div>
      </div>

      {/* Description Section */}
      <div className="section-card">
        <h3 className="section-title">Summary & Description</h3>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {game.description || 'No description provided.'}
        </p>
      </div>

      {/* Critic and User Summaries Section (AI placeholder) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
        <div className="section-card">
          <h3 className="section-title">Critic Summary (AI Insights)</h3>
          <p style={{ color: 'var(--text-secondary)', fontStyle: game.critic_summary ? 'normal' : 'italic' }}>
            {game.critic_summary || 'Critic consensus summary will be generated by AI in subsequent stages.'}
          </p>
        </div>

        <div className="section-card">
          <h3 className="section-title">User Reviews Consensus (AI Insights)</h3>
          <p style={{ color: 'var(--text-secondary)', fontStyle: game.user_summary ? 'normal' : 'italic' }}>
            {game.user_summary || 'Player sentiment consensus summary will be generated by AI in subsequent stages.'}
          </p>
        </div>
      </div>
    </div>
  );
};
