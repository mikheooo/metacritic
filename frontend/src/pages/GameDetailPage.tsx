import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { fetchGameById } from '../api/client';
import { GameDetail, Review } from '../types';
import { ScoreBadge } from '../components/ScoreBadge';
import { ProceduralCover } from '../components/ProceduralCover';

export const GameDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [game, setGame] = useState<GameDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'critic' | 'user'>('critic');
  const [imageError, setImageError] = useState(false);

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
        <p>Загрузка информации об игре...</p>
      </div>
    );
  }

  if (error || !game) {
    return (
      <div className="error-state">
        <h2>Игра не найдена</h2>
        <p>{error || 'Запрошенная игра не найдена в базе данных.'}</p>
        <Link to="/" className="back-btn" style={{ marginTop: '1.5rem', display: 'inline-flex' }}>
          ← Назад в каталог
        </Link>
      </div>
    );
  }

  const criticDetail = game.critic_summary_detail;
  const userDetail = game.user_summary_detail;

  const criticReviews = game.reviews.filter((r) => r.review_type === 'critic');
  const userReviews = game.reviews.filter((r) => r.review_type === 'user');
  const displayedReviews = activeTab === 'critic' ? criticReviews : userReviews;

  const formatDuration = (seconds?: number | null): string | null => {
    if (!seconds) return null;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h} ч ${m} мин`;
    return `${m} мин`;
  };

  const formatViews = (views?: number | null): string | null => {
    if (views === null || views === undefined) return null;
    if (views >= 1_000_000) return `${(views / 1_000_000).toFixed(1)} млн просмотров`;
    if (views >= 1_000) return `${(views / 1_000).toFixed(1)} тыс. просмотров`;
    return `${views} просмотров`;
  };

  return (
    <div className="detail-page">
      <Link to="/" className="back-btn">
        ← Назад в каталог
      </Link>

      <div className="detail-header">
        {Boolean(game.cover_url) && !imageError ? (
          <img
            src={game.cover_url!}
            alt={game.title}
            className="detail-cover"
            onError={() => setImageError(true)}
          />
        ) : (
          <div className="detail-cover" style={{ padding: 0, overflow: 'hidden' }}>
            <ProceduralCover
              title={game.title}
              subtitle={game.developer || 'Игра'}
              aspect="detail"
            />
          </div>
        )}

        <div className="detail-info">
          <h1 className="detail-title">{game.title}</h1>
          <p className="detail-meta">
            Разработчик: <strong>{game.developer || 'Неизвестен'}</strong> • Добавлено:{' '}
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
              Платформы и оценки
            </h4>
            {game.game_platforms.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                Оценки для платформ пока отсутствуют.
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
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Критики:</span>
                      <ScoreBadge score={gp.metascore} type="metascore" />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Игроки:</span>
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
              Открыть на Metacritic ↗
            </a>
          )}
        </div>
      </div>

      {/* Description Section */}
      <div className="section-card">
        <h3 className="section-title">Описание игры</h3>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {game.description || 'Описание отсутствует.'}
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
                <span>🎯</span> Мнение критиков
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
                  ? `${criticDetail.review_count_used} рецензий проанализировано`
                  : `${criticReviews.length} рецензий`}
              </span>
            </div>

            <p style={{ color: 'var(--text-primary)', lineHeight: 1.6, marginBottom: '1.25rem' }}>
              {criticDetail?.summary ||
                game.critic_summary ||
                'Саммари рецензий критиков пока формируется.'}
            </p>

            {criticDetail && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1rem' }}>
                {criticDetail.likes && criticDetail.likes.length > 0 && (
                  <div>
                    <h5 style={{ color: '#22c55e', fontSize: '0.85rem', marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Ключевые достоинства
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
                      Ключевые недостатки
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
              <span>AI-провайдер: {criticDetail.provider} ({criticDetail.model})</span>
              <span>Обновлено: {new Date(criticDetail.updated_at).toLocaleDateString()}</span>
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
                <span>🎮</span> Мнение игроков
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
                  ? `${userDetail.review_count_used} отзывов проанализировано`
                  : `${userReviews.length} отзывов`}
              </span>
            </div>

            <p style={{ color: 'var(--text-primary)', lineHeight: 1.6, marginBottom: '1.25rem' }}>
              {userDetail?.summary ||
                game.user_summary ||
                'Саммари отзывов игроков пока формируется.'}
            </p>

            {userDetail && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1rem' }}>
                {userDetail.likes && userDetail.likes.length > 0 && (
                  <div>
                    <h5 style={{ color: '#22c55e', fontSize: '0.85rem', marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Ключевые достоинства
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
                      Ключевые недостатки
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
              <span>AI-провайдер: {userDetail.provider} ({userDetail.model})</span>
              <span>Обновлено: {new Date(userDetail.updated_at).toLocaleDateString()}</span>
            </div>
          )}
        </div>
      </div>

      {/* Popular Let's Play Section */}
      <div className="section-card" style={{ marginBottom: '2rem' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            marginBottom: '1.25rem',
            borderBottom: '1px solid var(--border-color)',
            paddingBottom: '0.75rem',
          }}
        >
          <span style={{ fontSize: '1.25rem' }}>📺</span>
          <h3 className="section-title" style={{ margin: 0 }}>
            Популярное видеопрохождение (Let's Play)
          </h3>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
            YouTube Data API v3 и AI-анализ
          </span>
        </div>

        {!game.lets_play ? (
          <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: '1rem 0' }}>
            Видеопрохождение пока не добавлено.
          </p>
        ) : (
          <div>
            <div
              style={{
                display: 'flex',
                flexDirection: 'row',
                flexWrap: 'wrap',
                gap: '1.5rem',
                backgroundColor: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '1.25rem',
              }}
            >
              {/* Thumbnail Container */}
              <div
                style={{
                  position: 'relative',
                  width: '320px',
                  maxWidth: '100%',
                  flexShrink: 0,
                  borderRadius: '6px',
                  overflow: 'hidden',
                  backgroundColor: '#000',
                  aspectRatio: '16/9',
                }}
              >
                {game.lets_play.thumbnail_url ? (
                  <img
                    src={game.lets_play.thumbnail_url}
                    alt={game.lets_play.title}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                ) : (
                  <div
                    style={{
                      width: '100%',
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'var(--text-muted)',
                    }}
                  >
                    Превью отсутствует
                  </div>
                )}
                {game.lets_play.duration_seconds && (
                  <span
                    style={{
                      position: 'absolute',
                      bottom: '8px',
                      right: '8px',
                      backgroundColor: 'rgba(0, 0, 0, 0.8)',
                      color: '#fff',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '2px 6px',
                      borderRadius: '4px',
                    }}
                  >
                    {formatDuration(game.lets_play.duration_seconds)}
                  </span>
                )}
              </div>

              {/* Metadata & Actions */}
              <div style={{ flex: 1, minWidth: '260px', display: 'flex', flexDirection: 'column' }}>
                <h4 style={{ fontSize: '1.1rem', fontWeight: 600, margin: '0 0 0.5rem 0', lineHeight: 1.4 }}>
                  {game.lets_play.title}
                </h4>
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  {game.lets_play.channel_title && (
                    <span>Канал: <strong>{game.lets_play.channel_title}</strong></span>
                  )}
                  {game.lets_play.view_count !== null && (
                    <span>• {formatViews(game.lets_play.view_count)}</span>
                  )}
                  {game.lets_play.transcript && (
                    <span
                      style={{
                        backgroundColor: game.lets_play.transcript.is_generated ? 'rgba(59, 130, 246, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                        color: game.lets_play.transcript.is_generated ? '#60a5fa' : '#34d399',
                        padding: '2px 8px',
                        borderRadius: '12px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                      }}
                    >
                      {game.lets_play.transcript.is_generated ? 'Автосубтитры' : 'Официальные субтитры'} ({game.lets_play.transcript.language.toUpperCase()})
                    </span>
                  )}
                </div>

                {/* AI Summary or Unavailable Notice */}
                {game.lets_play.summary ? (
                  <div style={{ marginTop: '0.5rem' }}>
                    <p style={{ fontSize: '0.95rem', lineHeight: 1.6, color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
                      {game.lets_play.summary.text}
                    </p>
                    {game.lets_play.summary.key_points && game.lets_play.summary.key_points.length > 0 && (
                      <div style={{ marginBottom: '1rem' }}>
                        <strong style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          Ключевые моменты видеопрохождения
                        </strong>
                        <ul style={{ margin: '0.5rem 0 0 0', paddingLeft: '1.25rem', fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                          {game.lets_play.summary.key_points.map((pt, idx) => (
                            <li key={idx} style={{ marginBottom: '0.25rem' }}>{pt}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', margin: '0.75rem 0' }}>
                    Видео найдено, но транскрипт пока недоступен.
                  </p>
                )}

                {/* Watch Button */}
                <div style={{ marginTop: 'auto', paddingTop: '0.75rem' }}>
                  <a
                    href={game.lets_play.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      backgroundColor: '#ef4444',
                      color: '#fff',
                      padding: '0.5rem 1rem',
                      borderRadius: '6px',
                      textDecoration: 'none',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      transition: 'background-color 0.2s ease',
                    }}
                  >
                    ▶ Смотреть на YouTube
                  </a>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Similar Games Section */}
      <div className="section-card" style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.25rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
          <span style={{ fontSize: '1.25rem' }}>🎮</span>
          <h3 className="section-title" style={{ margin: 0 }}>
            Похожие игры
          </h3>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
            Семантический pgvector поиск
          </span>
        </div>

        {(!game.similar_games || game.similar_games.length === 0) ? (
          <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: '1rem 0' }}>
            Похожие игры пока формируются.
          </p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1.25rem' }}>
            {game.similar_games.map((sim) => {
              const matchPercent = Math.round(sim.similarity_score * 100);
              return (
                <Link
                  key={sim.id}
                  to={`/games/${sim.id}`}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    backgroundColor: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    overflow: 'hidden',
                    textDecoration: 'none',
                    color: 'inherit',
                    transition: 'transform 0.2s, border-color 0.2s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-4px)';
                    e.currentTarget.style.borderColor = 'var(--accent-primary)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.borderColor = 'var(--border-color)';
                  }}
                >
                  <div style={{ width: '100%', height: '140px', backgroundColor: 'rgba(0,0,0,0.3)', position: 'relative' }}>
                    {sim.cover_url ? (
                      <img
                        src={sim.cover_url}
                        alt={sim.title}
                        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      />
                    ) : (
                      <ProceduralCover
                        title={sim.title}
                        aspect="thumb"
                      />
                    )}
                    <span
                      style={{
                        position: 'absolute',
                        top: '8px',
                        right: '8px',
                        backgroundColor: matchPercent >= 80 ? 'rgba(16, 185, 129, 0.9)' : 'rgba(59, 130, 246, 0.9)',
                        color: '#fff',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '12px',
                        backdropFilter: 'blur(4px)',
                      }}
                    >
                      {matchPercent}% совпадение
                    </span>
                  </div>
                  <div style={{ padding: '0.75rem 1rem', display: 'flex', flexDirection: 'column', flex: 1 }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.95rem', fontWeight: 600, lineHeight: 1.3 }}>
                      {sim.title}
                    </h4>
                    {sim.platforms && sim.platforms.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem', marginTop: 'auto' }}>
                        {sim.platforms.slice(0, 3).map((p, idx) => (
                          <span
                            key={idx}
                            style={{
                              fontSize: '0.7rem',
                              backgroundColor: 'rgba(255, 255, 255, 0.08)',
                              padding: '1px 6px',
                              borderRadius: '4px',
                              color: 'var(--text-secondary)',
                            }}
                          >
                            {p}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>

      {/* Reviews List Section with Tabs */}
      <div className="section-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
          <h3 className="section-title" style={{ margin: 0 }}>
            Отзывы и рецензии
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
              Критики ({criticReviews.length})
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
              Игроки ({userReviews.length})
            </button>
          </div>
        </div>

        {displayedReviews.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', padding: '1rem 0' }}>
            Отзывы {activeTab === 'critic' ? 'критиков' : 'игроков'} для этой игры пока отсутствуют.
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
                    <strong style={{ fontSize: '0.95rem' }}>{r.author || 'Аноним'}</strong>
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
