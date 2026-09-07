import React from 'react';
import { Link, useLocation } from 'react-router-dom';

export const Header: React.FC = () => {
  const location = useLocation();

  return (
    <header className="header">
      <div className="header-content">
        <Link to="/" className="logo-group">
          <div className="logo-icon">M</div>
          <span className="logo-title">Metacritic AI</span>
        </Link>
        <nav className="nav-links">
          <Link
            to="/"
            className={`nav-link ${location.pathname === '/' ? 'active' : ''}`}
          >
            Games
          </Link>
          <Link
            to="/monitor"
            className={`nav-link ${location.pathname === '/monitor' ? 'active' : ''}`}
          >
            Monitoring
          </Link>
        </nav>
      </div>
    </header>
  );
};
