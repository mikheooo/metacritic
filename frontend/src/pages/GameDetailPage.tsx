import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchGameById } from '../api/client';
import { GameDetail, Review } from '../types';
import { ScoreBadge } from '../components/ScoreBadge';

export const GameDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [game, setGame] = useState<GameDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'critic' | 'user'>('critic');

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

  const criticDetail = game.critic_summary_detail;
  const userDetail = game.user_summary_detail;

  const criticReviews = game.reviews.filter((r) => r.review_type === 'critic');
  const userReviews = game.reviews.filter((r) => r.review_type === 'user');
  const displayedReviews = activeTab === 'critic' ? criticReviews : userReviews;

  return (
    <div className="detail-page">
      <Link to="/" className="back-btn">
        ← Back to Catalog
      </Link>

      <div className="detail-header">
        {game.cover_url ? (
          <img src={game.cover_url} alt={game.title} className="detail-cover" />
        ) : (
          <div
            className="detail-cover"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-muted)',
            }}
          >
            No Cover Available
          </div>
        )}

        <div className="detail-info">
          <h1 className="detail-title">{game.title}</h1>
          <p className="detail-meta">
            Developed by <strong>{game.developer || 'Unknown'}</strong> • Added{' '}
            {new Date(game.created_at).toLocaleDateString()}
          </p>

          <div style={{ marginBottom: '1.5rem' }}>
            <h4
              style={{
                fontSize: '0.9rem',
                color: 'var(--text-muted)',
                marginBottom: '0.5rem',
                textTransform: 'uppercase',
              }}
            >
              Platforms & Scores
            </h4>
            {game.game_platforms.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                No platform scores registered yet.
              </p>
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
        <h3 className="section-title">Overview</h3>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {game.description || 'No description provided.'}
        </p>
      </div>

      {/* AI Summaries Section: Critics Say vs Players Say */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
          gap: '1.5rem',
          marginBottom: '2rem',
        }}
      >
        {/* Critics Say Card */}
        <div
          className="section-card"
          style={{
            borderTop: '3px solid #6366f1',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '1rem',
              }}
            >
              <h3 className="section-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span>🎯</span> Critics say
              </h3>
              <span
                style={{
                  fontSize: '0.75rem',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '999px',
                  backgroundColor: 'rgba(99, 102, 241, 0.15)',
                  color: '#818cf8',
                  fontWeight: 600,
                }}
              >
                {criticDetail
                  ? `${criticDetail.review_count_used} reviews analyzed`
                  : `${criticReviews.length} reviews`}
              </span>
            </div>

            <p style={{ color: 'var(--text-primary)', lineHeight: 1.6, marginBottom: '1.25rem' }}>
              {criticDetail?.summary ||
                game.critic_summary ||
                'Critic reviews have not been summarized yet.'}
            </p>

            {criticDetail && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1rem' }}>
                {criticDetail.likes && criticDetail.likes.length > 0 && (
                  <div>
                    <h5 style={{ color: '#22c55e', fontSize: '0.85rem', marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Key Strengths (Likes)
                    </h5>
                    <ul style={{ listStyle: 'none', paddingLeft: 0, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      {criticDetail.likes.map((like, idx) => (
                        <li key={idx} style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                          <span style={{ color: '#22c55e', fontWeight: 'bold' }}>✓</span>
                          <span>{like}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {criticDetail.dislikes && criticDetail.dislikes.length > 0 && (
                  <div>
                    <h5 style={{ color: '#ef4444', fontSize: '0.85rem', marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Key Drawbacks (Dislikes)
                    </h5>
                    <ul style={{ listStyle: 'none', paddingLeft: 0, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      {criticDetail.dislikes.map((dislike, idx) => (
                        <li key={idx} style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                          <span style={{ color: '#ef4444', fontWeight: 'bold' }}>✗</span>
                          <span>{dislike}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>

          {criticDetail && (
            <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-color)', fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
              <span>Provider: {criticDetail.provider} ({criticDetail.model})</span>
              <span>Updated: {new Date(criticDetail.updated_at).toLocaleDateString()}</span>
            </div>
          )}
        </div>

        {/* Players Say Card */}
        <div
          className="section-card"
          style={{
            borderTop: '3px solid #10b981',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '1rem',
              }}
            >
              <h3 className="section-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span>🎮</span> Players say
              </h3>
              <span
                style={{
                  fontSize: '0.75rem',
                  padding: '0.2rem 0.6rem',
                  borderRadius: '999px',
                  backgroundColor: 'rgba(16, 185, 129, 0.15)',
                  color: '#34d399',
                  fontWeight: 600,
                }}
              >
                {userDetail
                  ? `${userDetail.review_count_used} reviews analyzed`
                  : `${userReviews.length} reviews`}
              </span>
            </div>

            <p style={{ color: 'var(--text-primary)', lineHeight: 1.6, marginBottom: '1.25rem' }}>
              {userDetail?.summary ||
                game.user_summary ||
                'Player reviews have not been summarized yet.'}
            </p>

            {userDetail && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1rem' }}>
                {userDetail.likes && userDetail.likes.length > 0 && (
                  <div>
                    <h5 style={{ color: '#22c55e', fontSize: '0.85rem', marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Key Strengths (Likes)
                    </h5>
                    <ul style={{ listStyle: 'none', paddingLeft: 0, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      {userDetail.likes.map((like, idx) => (
                        <li key={idx} style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                          <span style={{ color: '#22c55e', fontWeight: 'bold' }}>✓</span>
                          <span>{like}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {userDetail.dislikes && userDetail.dislikes.length > 0 && (
                  <div>
                    <h5 style={{ color: '#ef4444', fontSize: '0.85rem', marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Key Drawbacks (Dislikes)
                    </h5>
                    <ul style={{ listStyle: 'none', paddingLeft: 0, display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      {userDetail.dislikes.map((dislike, idx) => (
                        <li key={idx} style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                          <span style={{ color: '#ef4444', fontWeight: 'bold' }}>✗</span>
                          <span>{dislike}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>

          {userDetail && (
            <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-color)', fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
              <span>Provider: {userDetail.provider} ({userDetail.model})</span>
              <span>Updated: {new Date(userDetail.updated_at).toLocaleDateString()}</span>
            </div>
          )}
        </div>
      </div>

      {/* Reviews List Section with Tabs */}
      <div className="section-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
          <h3 className="section-title" style={{ margin: 0 }}>
            Individual Reviews
          </h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={() => setActiveTab('critic')}
              style={{
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: 600,
                backgroundColor: activeTab === 'critic' ? 'var(--accent-primary)' : 'rgba(255,255,255,0.05)',
                color: activeTab === 'critic' ? '#fff' : 'var(--text-secondary)',
              }}
            >
              Critics ({criticReviews.length})
            </button>
            <button
              onClick={() => setActiveTab('user')}
              style={{
                padding: '0.4rem 0.8rem',
                borderRadius: '6px',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: 600,
                backgroundColor: activeTab === 'user' ? '#10b981' : 'rgba(255,255,255,0.05)',
                color: activeTab === 'user' ? '#fff' : 'var(--text-secondary)',
              }}
            >
              Players ({userReviews.length})
            </button>
          </div>
        </div>

        {displayedReviews.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: '1rem 0' }}>
            No {activeTab === 'critic' ? 'critic' : 'player'} reviews ingested for this game yet.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {displayedReviews.map((r: Review) => (
              <div
                key={r.id}
                style={{
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '8px',
                  padding: '1rem 1.25rem',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <ScoreBadge
                      score={r.rating}
                      type={r.review_type === 'critic' ? 'metascore' : 'userscore'}
                    />
                    <strong style={{ fontSize: '0.95rem' }}>{r.author || 'Anonymous'}</strong>
                  </div>
                  {r.published_at && (
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {new Date(r.published_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.6, margin: '0.5rem 0' }}>
                  {r.body}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
