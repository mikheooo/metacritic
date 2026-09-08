import React from 'react';

interface ProceduralCoverProps {
  title: string;
  subtitle?: string;
  className?: string;
  style?: React.CSSProperties;
  aspect?: 'card' | 'detail' | 'thumb';
}

const PALETTES = [
  { from: '#c2410c', via: '#9f1239', to: '#1e1b4b', text: '#ffedd5', accent: '#fde047', badgeBg: 'rgba(194, 65, 12, 0.4)', badgeBorder: 'rgba(253, 224, 71, 0.3)' }, // Warm Ember
  { from: '#0284c7', via: '#1e3a8a', to: '#020617', text: '#e0f2fe', accent: '#38bdf8', badgeBg: 'rgba(2, 132, 199, 0.4)', badgeBorder: 'rgba(56, 189, 248, 0.3)' }, // Cyber Neon
  { from: '#059669', via: '#134e4a', to: '#051b14', text: '#d1fae5', accent: '#34d399', badgeBg: 'rgba(5, 150, 105, 0.4)', badgeBorder: 'rgba(52, 211, 153, 0.3)' }, // Deep Emerald
  { from: '#7c3aed', via: '#701a75', to: '#0f172a', text: '#f3e8ff', accent: '#c084fc', badgeBg: 'rgba(124, 58, 237, 0.4)', badgeBorder: 'rgba(192, 132, 252, 0.3)' }, // Cosmic Violet
  { from: '#dc2626', via: '#831843', to: '#18181b', text: '#fee2e2', accent: '#f87171', badgeBg: 'rgba(220, 38, 38, 0.4)', badgeBorder: 'rgba(248, 113, 113, 0.3)' }, // Crimson Noir
  { from: '#4f46e5', via: '#1d4ed8', to: '#090d16', text: '#e0e7ff', accent: '#818cf8', badgeBg: 'rgba(79, 70, 229, 0.4)', badgeBorder: 'rgba(129, 140, 248, 0.3)' }, // Royal Sapphire
  { from: '#d97706', via: '#78350f', to: '#1c1917', text: '#fef3c7', accent: '#fcd34d', badgeBg: 'rgba(217, 119, 6, 0.4)', badgeBorder: 'rgba(252, 211, 77, 0.3)' }, // Golden Bronze
  { from: '#0d9488', via: '#0369a1', to: '#081726', text: '#ccfbf1', accent: '#2dd4bf', badgeBg: 'rgba(13, 148, 136, 0.4)', badgeBorder: 'rgba(45, 212, 191, 0.3)' }, // Oceanic Teal
];

function getPalette(str: string) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  const index = Math.abs(hash) % PALETTES.length;
  return { palette: PALETTES[index], seed: Math.abs(hash) };
}

export const ProceduralCover: React.FC<ProceduralCoverProps> = ({
  title,
  subtitle,
  className = '',
  style = {},
  aspect = 'card',
}) => {
  const { palette, seed } = getPalette(title || 'game');

  const iconType = seed % 4;
  const isDetail = aspect === 'detail';
  const isThumb = aspect === 'thumb';

  return (
    <div
      className={`procedural-cover ${className}`}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        background: `linear-gradient(135deg, ${palette.from} 0%, ${palette.via} 50%, ${palette.to} 100%)`,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        padding: isThumb ? '0.5rem' : isDetail ? '1.5rem' : '1rem',
        boxSizing: 'border-box',
        overflow: 'hidden',
        userSelect: 'none',
        ...style,
      }}
    >
      {/* Subtle Dot Mesh Background Pattern */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'radial-gradient(rgba(255, 255, 255, 0.09) 1px, transparent 1px)',
          backgroundSize: isThumb ? '8px 8px' : '14px 14px',
          pointerEvents: 'none',
        }}
      />

      {/* Subtle diagonal ambient light */}
      <div
        style={{
          position: 'absolute',
          top: '-20%',
          right: '-20%',
          width: '70%',
          height: '70%',
          borderRadius: '50%',
          background: `radial-gradient(circle, ${palette.accent}22 0%, transparent 70%)`,
          pointerEvents: 'none',
        }}
      />

      {/* Top Header Row */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          width: '100%',
        }}
      >
        <span
          style={{
            fontSize: isThumb ? '0.6rem' : '0.68rem',
            fontFamily: 'monospace',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            padding: isThumb ? '1px 4px' : '2px 8px',
            borderRadius: '4px',
            backgroundColor: palette.badgeBg,
            border: `1px solid ${palette.badgeBorder}`,
            color: palette.text,
            backdropFilter: 'blur(4px)',
          }}
        >
          {subtitle || 'Catalog'}
        </span>

        {/* Minimal geometric badge */}
        <svg
          width={isThumb ? 12 : 16}
          height={isThumb ? 12 : 16}
          viewBox="0 0 24 24"
          fill="none"
          stroke={palette.accent}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ opacity: 0.75 }}
        >
          {iconType === 0 && (
            <>
              <rect x="2" y="6" width="20" height="12" rx="2" />
              <path d="M6 12h4m-2-2v4" />
              <circle cx="17" cy="10" r="0.5" fill="currentColor" />
              <circle cx="15" cy="13" r="0.5" fill="currentColor" />
            </>
          )}
          {iconType === 1 && (
            <>
              <path d="M12 2l2.4 7.4H22l-6 4.6 2.3 7.4L12 17l-6.3 4.4 2.3-7.4-6-4.6h7.6z" />
            </>
          )}
          {iconType === 2 && (
            <>
              <polygon points="12 2 19 12 12 22 5 12" />
              <circle cx="12" cy="12" r="2" />
            </>
          )}
          {iconType === 3 && (
            <>
              <polygon points="5 3 19 12 5 21 5 3" />
            </>
          )}
        </svg>
      </div>

      {/* Middle: Title & Poster Typography */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          margin: isThumb ? '0.25rem 0' : '0.75rem 0',
        }}
      >
        {!isThumb && (
          <div
            style={{
              fontSize: isDetail ? '0.75rem' : '0.62rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.12em',
              color: palette.accent,
              marginBottom: '0.35rem',
              opacity: 0.9,
            }}
          >
            Metacritic Release
          </div>
        )}
        <h4
          style={{
            margin: 0,
            fontSize: isThumb ? '0.75rem' : isDetail ? '1.4rem' : '1.05rem',
            fontWeight: 800,
            lineHeight: 1.2,
            color: '#ffffff',
            textShadow: '0 2px 8px rgba(0,0,0,0.5)',
            display: '-webkit-box',
            WebkitLineClamp: isThumb ? 2 : isDetail ? 4 : 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            wordBreak: 'break-word',
          }}
        >
          {title}
        </h4>
      </div>

      {/* Bottom Footer Row */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderTop: '1px solid rgba(255, 255, 255, 0.12)',
          paddingTop: isThumb ? '0.25rem' : '0.5rem',
          fontSize: isThumb ? '0.55rem' : '0.65rem',
          color: 'rgba(255, 255, 255, 0.65)',
          fontFamily: 'monospace',
        }}
      >
        <span>No Box Art</span>
        <span style={{ color: palette.accent, fontWeight: 700 }}>Procedural</span>
      </div>
    </div>
  );
};
