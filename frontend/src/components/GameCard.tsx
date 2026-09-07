import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Game } from '../types';
import { ScoreBadge } from './ScoreBadge';

interface GameCardProps {
  game: Game;
}

export const GameCard: React.FC<GameCardProps> = ({ game }) => {
  const navigate = useNavigate();

  // Extract best metascore & userscore
  const metascores = game.game_platforms
    .map((gp) => gp.metascore)
    .filter((s): s is number => s !== null);
  const bestMetascore = metascores.length > 0 ? Math.max(...metascores) : null;

  const userscores = game.game_platforms
    .map((gp) => gp.userscore)
    .filter((s): s is number => s !== null);
  const bestUserscore = userscores.length > 0 ? Math.max(...userscores) : null;

  const platformNames = game.game_platforms
    .map((gp) => gp.platform.name)
    .join(', ');

  return (
    <div className="game-card" onClick={() => navigate(`/games/${game.id}`)}>
      {game.cover_url ? (
        <img
          src={game.cover_url}
          alt={game.title}
          className="game-cover"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
      ) : (
        <div className="game-cover">No Cover</div>
      )}

      <div className="game-card-body">
        <h3 className="game-card-title">{game.title}</h3>
        <p className="game-card-dev">{game.developer || 'Unknown Developer'}</p>
        {platformNames && (
          <p className="game-card-dev" style={{ color: 'var(--accent-primary)', marginBottom: '0.5rem' }}>
            {platformNames}
          </p>
        )}

        <div className="game-card-scores">
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block' }}>Metascore</span>
            <ScoreBadge score={bestMetascore} type="metascore" />
          </div>
          <div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', textAlign: 'right' }}>User Score</span>
            <ScoreBadge score={bestUserscore} type="userscore" />
          </div>
        </div>
      </div>
    </div>
  );
};
