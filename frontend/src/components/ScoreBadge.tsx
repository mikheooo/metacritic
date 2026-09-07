import React from 'react';

interface ScoreBadgeProps {
  score: number | null;
  type: 'metascore' | 'userscore';
}

export const ScoreBadge: React.FC<ScoreBadgeProps> = ({ score, type }) => {
  if (score === null || score === undefined) {
    return (
      <span className={`score-badge score-${type} score-none`}>
        tbd
      </span>
    );
  }

  let colorClass = 'score-none';
  if (type === 'metascore') {
    if (score >= 75) colorClass = 'score-high';
    else if (score >= 50) colorClass = 'score-mid';
    else colorClass = 'score-low';
  } else {
    if (score >= 7.5) colorClass = 'score-high';
    else if (score >= 5.0) colorClass = 'score-mid';
    else colorClass = 'score-low';
  }

  const formattedScore = type === 'userscore' ? score.toFixed(1) : Math.round(score);

  return (
    <span className={`score-badge score-${type} ${colorClass}`}>
      {formattedScore}
    </span>
  );
};
