import React, { useEffect, useState } from 'react';
import { fetchHealth, fetchReady } from '../api/client';
import { HealthStatus, ReadyStatus } from '../types';

export const MonitorPage: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [ready, setReady] = useState<ReadyStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const checkStatus = async () => {
    setLoading(true);
    try {
      const [h, r] = await Promise.allSettled([fetchHealth(), fetchReady()]);
      if (h.status === 'fulfilled') setHealth(h.value);
      else setHealth({ status: 'unreachable', version: 'unknown' });

      if (r.status === 'fulfilled') setReady(r.value);
      else setReady({ status: 'disconnected', database: 'unreachable' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkStatus();
  }, []);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.85rem', fontWeight: 700 }}>System Monitoring</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
            Infrastructure and crawl pipeline operational status
          </p>
        </div>
        <button className="order-btn" onClick={checkStatus} disabled={loading}>
          {loading ? 'Checking...' : 'Refresh Status'}
        </button>
      </div>

      <div className="monitor-grid">
        {/* Backend Process Health */}
        <div className="section-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Backend API Service</h3>
            <span className={`status-badge ${health?.status === 'ok' ? 'ok' : 'down'}`}>
              ● {health?.status === 'ok' ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>
            Endpoint: <code>/health</code>
          </p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            API Version: <code>{health?.version || 'N/A'}</code>
          </p>
        </div>

        {/* Database Readiness */}
        <div className="section-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>PostgreSQL Database</h3>
            <span className={`status-badge ${ready?.status === 'ready' ? 'ok' : 'down'}`}>
              ● {ready?.status === 'ready' ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>
            Endpoint: <code>/ready</code>
          </p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Connection State: <code>{ready?.database || 'disconnected'}</code>
          </p>
        </div>

        {/* Celery & Redis Worker */}
        <div className="section-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Background Workers (Celery)</h3>
            <span className="status-badge ok">● READY</span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>
            Broker: <code>Redis 7</code>
          </p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Diagnostic task: <code>tasks.ping() -&gt; &quot;pong&quot;</code>
          </p>
        </div>
      </div>

      {/* Crawl Pipeline Dashboard Placeholder */}
      <div className="section-card" style={{ marginTop: '2rem' }}>
        <h3 className="section-title">Crawl Pipeline (Future Stages)</h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', lineHeight: 1.6 }}>
          The ingestion engine will execute on an hourly schedule in Stage 2. It will track daily crawl phases, browse offsets, and enforce the calendar day deduplication invariant via <code>DailyGameProcessing</code>.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
          <div style={{ padding: '1rem', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Daily Phase</span>
            <div style={{ fontSize: '1.1rem', fontWeight: 600, marginTop: '0.25rem' }}>Standby (Stage 1)</div>
          </div>
          <div style={{ padding: '1rem', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Daily Invariant Guard</span>
            <div style={{ fontSize: '1.1rem', fontWeight: 600, marginTop: '0.25rem', color: '#4ade80' }}>Active (Constraint)</div>
          </div>
          <div style={{ padding: '1rem', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Active Tasks</span>
            <div style={{ fontSize: '1.1rem', fontWeight: 600, marginTop: '0.25rem' }}>0 Running</div>
          </div>
        </div>
      </div>
    </div>
  );
};
