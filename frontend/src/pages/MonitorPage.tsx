import React, { useEffect, useRef, useState } from 'react';
import { fetchMonitorRuns, fetchMonitorStatus, triggerRunNow } from '../api/client';
import { CrawlRun, CrawlRunEvent, MonitorStatus, PipelineStage } from '../types';

export const MonitorPage: React.FC = () => {
  const [statusData, setStatusData] = useState<MonitorStatus | null>(null);
  const [runs, setRuns] = useState<CrawlRun[]>([]);
  const [events, setEvents] = useState<CrawlRunEvent[]>([]);
  const [selectedRun, setSelectedRun] = useState<CrawlRun | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [runNowLoading, setRunNowLoading] = useState<boolean>(false);
  const [runNowError, setRunNowError] = useState<string | null>(null);
  const [runNowSuccess, setRunNowSuccess] = useState<string | null>(null);
  const [sseConnected, setSseConnected] = useState<boolean>(false);
  const [currentTime, setCurrentTime] = useState<string>(new Date().toUTCString());

  const eventSourceRef = useRef<EventSource | null>(null);

  // Live UTC Clock
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date().toUTCString());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch initial monitoring status and runs
  const loadInitialData = async () => {
    try {
      setLoading(true);
      const [st, rn] = await Promise.all([
        fetchMonitorStatus().catch(() => null),
        fetchMonitorRuns(20, 0).catch(() => []),
      ]);
      if (st) {
        setStatusData(st);
        if (st.active_run?.events && st.active_run.events.length > 0) {
          setEvents(st.active_run.events);
        } else if (st.last_run?.events && st.last_run.events.length > 0) {
          setEvents(st.last_run.events);
        }
      }
      setRuns(rn);
    } catch (err) {
      console.error('Failed to load initial monitor data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  // Server-Sent Events (SSE) Realtime Stream
  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource('/api/monitor/stream');
      eventSourceRef.current = es;

      es.onopen = () => {
        setSseConnected(true);
      };

      es.addEventListener('snapshot', (e: MessageEvent) => {
        try {
          const snapshot: MonitorStatus = JSON.parse(e.data);
          setStatusData(snapshot);
        } catch (err) {
          console.warn('Error parsing snapshot event:', err);
        }
      });

      es.addEventListener('event', (e: MessageEvent) => {
        try {
          const newEvent: CrawlRunEvent = JSON.parse(e.data);
          setEvents((prev) => {
            if (prev.some((item) => item.id === newEvent.id)) return prev;
            return [...prev, newEvent];
          });

          // Refresh status and runs when a run finishes or starts
          if (
            newEvent.event_type.startsWith('run_') ||
            newEvent.event_type === 'discovery_completed'
          ) {
            fetchMonitorStatus()
              .then(setStatusData)
              .catch(() => {});
            fetchMonitorRuns(20, 0)
              .then(setRuns)
              .catch(() => {});
          }
        } catch (err) {
          console.warn('Error parsing SSE event:', err);
        }
      });

      es.onerror = () => {
        setSseConnected(false);
      };
    } catch (err) {
      console.warn('Failed to establish EventSource:', err);
      setSseConnected(false);
    }

    // Polling fallback every 10 seconds
    const pollTimer = setInterval(() => {
      fetchMonitorStatus()
        .then(setStatusData)
        .catch(() => {});
      fetchMonitorRuns(20, 0)
        .then(setRuns)
        .catch(() => {});
    }, 10000);

    return () => {
      if (es) es.close();
      clearInterval(pollTimer);
    };
  }, []);

  // Run Now trigger handler
  const handleRunNow = async () => {
    if (runNowLoading || statusData?.active_run) return;

    setRunNowLoading(true);
    setRunNowError(null);
    setRunNowSuccess(null);

    try {
      const resp = await triggerRunNow();
      setRunNowSuccess(`Run #${resp.run_id} queued successfully.`);
      // Refresh status immediately
      const updated = await fetchMonitorStatus();
      setStatusData(updated);
      const updatedRuns = await fetchMonitorRuns(20, 0);
      setRuns(updatedRuns);
    } catch (err: any) {
      if (err.status === 409) {
        setRunNowError(
          err.message || 'A Metacritic processing run is already active. Please wait for it to complete.'
        );
      } else {
        setRunNowError(err.message || 'Failed to trigger run.');
      }
    } finally {
      setRunNowLoading(false);
    }
  };

  const activeRun = statusData?.active_run;
  const lastRun = statusData?.last_run;
  const currentDisplayRun = activeRun || lastRun;

  // Calculate progress percentage
  const targetCount = currentDisplayRun?.target_count || 20;
  const processedCount = currentDisplayRun?.processed_count || 0;
  const failedCount = currentDisplayRun?.failed_count || 0;
  const progressPercent = Math.min(
    100,
    Math.round(((processedCount + failedCount) / (targetCount || 1)) * 100)
  );

  const STAGES: PipelineStage[] = [
    'discovering' as PipelineStage,
    'ingesting' as PipelineStage,
    'reviews' as PipelineStage,
    'summarizing' as PipelineStage,
    'embedding' as PipelineStage,
    'youtube' as PipelineStage,
    'similarity' as PipelineStage,
  ];

  if (loading && !statusData) {
    return (
      <div className="loading-state">
        <div className="spinner"></div>
        <p>Loading monitor telemetry...</p>
      </div>
    );
  }

  return (
    <div>
      {/* Header with Title and Run Now Button */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          marginBottom: '1.5rem',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.85rem', fontWeight: 700 }}>System Monitoring</h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
            Realtime crawl pipeline, hourly scheduler, worker telemetry & event stream
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button
            className="btn-run-now"
            onClick={handleRunNow}
            disabled={runNowLoading || !!activeRun}
            title={activeRun ? 'A run is currently in progress' : 'Trigger on-demand pipeline run'}
          >
            {runNowLoading ? (
              <>⏳ Queueing Run...</>
            ) : activeRun ? (
              <>⚙️ Run #{activeRun.id} Active</>
            ) : (
              <>▶ Run Now</>
            )}
          </button>
        </div>
      </div>

      {/* Conflict / Error Banner */}
      {runNowError && (
        <div
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            color: '#f87171',
            padding: '0.85rem 1.25rem',
            borderRadius: '8px',
            marginBottom: '1.5rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>⚠️ {runNowError}</span>
          <button
            style={{ background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', fontWeight: 700 }}
            onClick={() => setRunNowError(null)}
          >
            ✕
          </button>
        </div>
      )}

      {/* Success Banner */}
      {runNowSuccess && (
        <div
          style={{
            backgroundColor: 'rgba(34, 197, 94, 0.15)',
            border: '1px solid rgba(34, 197, 94, 0.4)',
            color: '#4ade80',
            padding: '0.85rem 1.25rem',
            borderRadius: '8px',
            marginBottom: '1.5rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>✓ {runNowSuccess}</span>
          <button
            style={{ background: 'none', border: 'none', color: '#4ade80', cursor: 'pointer', fontWeight: 700 }}
            onClick={() => setRunNowSuccess(null)}
          >
            ✕
          </button>
        </div>
      )}

      {/* System Status Grid */}
      <div className="monitor-grid">
        {/* Scheduler Status */}
        <div className="section-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Hourly Scheduler (Beat)</h3>
            <span
              className={`status-badge ${statusData?.scheduler.enabled ? 'ok' : 'down'}`}
            >
              ● {statusData?.scheduler.enabled ? 'ENABLED' : 'DISABLED'}
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.4rem' }}>
            Timezone: <code>{statusData?.scheduler.timezone || 'UTC'}</code>
          </p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.4rem' }}>
            Next Run: <code>{statusData?.scheduler.next_run_at ? new Date(statusData.scheduler.next_run_at).toUTCString() : 'N/A'}</code>
          </p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Last Run: <code>{statusData?.scheduler.last_run_at ? new Date(statusData.scheduler.last_run_at).toUTCString() : 'None recorded'}</code>
          </p>
        </div>

        {/* Worker Telemetry */}
        <div className="section-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Celery Background Worker</h3>
            <span
              className={`status-badge ${
                statusData?.worker.online ? 'ok' : statusData ? 'down' : 'warning'
              }`}
            >
              ● {statusData?.worker.online ? 'ONLINE' : statusData ? 'OFFLINE' : 'UNKNOWN'}
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.4rem' }}>
            Worker Nodes: <code>{statusData?.worker.workers.length ? statusData.worker.workers.join(', ') : 'No active workers responded'}</code>
          </p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.4rem' }}>
            Broker: <code>Redis 7 (Distributed Lock Guard)</code>
          </p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Task: <code>tasks.process_metacritic_pipeline</code>
          </p>
        </div>

        {/* Realtime Stream & Clock */}
        <div className="section-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>System Clock & Stream</h3>
            <span className={`status-badge ${sseConnected ? 'ok' : 'warning'}`}>
              ● {sseConnected ? 'LIVE SSE' : 'CONNECTING'}
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.4rem' }}>
            Current UTC Time: <code style={{ color: '#f8fafc', fontWeight: 600 }}>{currentTime}</code>
          </p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.4rem' }}>
            Stream Channel: <code>/api/monitor/stream</code>
          </p>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Durability: <code>PostgreSQL Append-Only Log</code>
          </p>
        </div>
      </div>

      {/* Active Run / Latest Run Dashboard */}
      <div className="section-card" style={{ marginTop: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
          <div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 700 }}>
              {activeRun ? `ACTIVE RUN #${activeRun.id}` : lastRun ? `LAST RUN #${lastRun.id}` : 'PIPELINE STANDBY'}
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              {currentDisplayRun
                ? `Trigger: ${currentDisplayRun.trigger_type.toUpperCase()} • Started: ${new Date(currentDisplayRun.created_at).toUTCString()}`
                : 'No pipeline execution recorded yet'}
            </p>
          </div>

          {currentDisplayRun && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <span
                className={`status-badge ${
                  currentDisplayRun.status === 'completed'
                    ? 'ok'
                    : currentDisplayRun.status === 'running'
                    ? 'info'
                    : currentDisplayRun.status === 'partial'
                    ? 'warning'
                    : 'down'
                }`}
              >
                ● {currentDisplayRun.status.toUpperCase()}
              </span>
              {currentDisplayRun.current_stage && (
                <span className="stage-pill">STAGE: {currentDisplayRun.current_stage}</span>
              )}
            </div>
          )}
        </div>

        {/* Current Game & Stage Progress Bar */}
        {currentDisplayRun && (
          <div>
            {currentDisplayRun.current_game_title && (
              <div style={{ marginBottom: '0.75rem', fontSize: '0.95rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Current Game: </span>
                <strong style={{ color: '#818cf8' }}>{currentDisplayRun.current_game_title}</strong>
              </div>
            )}

            {/* Pipeline Stage Steps Indicator */}
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', margin: '1rem 0' }}>
              {STAGES.map((st) => {
                const isActive = currentDisplayRun.current_stage === st;
                return (
                  <span
                    key={st}
                    style={{
                      padding: '0.35rem 0.75rem',
                      borderRadius: '6px',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      backgroundColor: isActive ? 'rgba(99, 102, 241, 0.25)' : 'rgba(255, 255, 255, 0.03)',
                      color: isActive ? '#a5b4fc' : 'var(--text-muted)',
                      border: isActive ? '1px solid #6366f1' : '1px solid var(--border-color)',
                      transition: 'all 0.2s ease',
                    }}
                  >
                    {isActive ? '▶ ' : ''}{st}
                  </span>
                );
              })}
            </div>

            {/* Progress Bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              <span>Progress: {processedCount + failedCount} of {targetCount} games processed</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="progress-container">
              <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
            </div>

            {/* Counter Matrix */}
            <div className="counter-grid">
              <div className="counter-box">
                <span className="counter-label">Games Processed</span>
                <span className="counter-value" style={{ color: '#4ade80' }}>
                  {currentDisplayRun.processed_count}
                </span>
              </div>
              <div className="counter-box">
                <span className="counter-label">Games Failed</span>
                <span className="counter-value" style={{ color: currentDisplayRun.failed_count > 0 ? '#f87171' : 'inherit' }}>
                  {currentDisplayRun.failed_count}
                </span>
              </div>
              <div className="counter-box">
                <span className="counter-label">Reviews Ingested</span>
                <span className="counter-value">
                  {currentDisplayRun.reviews_processed_count}
                </span>
              </div>
              <div className="counter-box">
                <span className="counter-label">AI Summaries</span>
                <span className="counter-value">
                  {currentDisplayRun.summaries_generated_count}
                </span>
              </div>
              <div className="counter-box">
                <span className="counter-label">Embeddings</span>
                <span className="counter-value">
                  {currentDisplayRun.embeddings_generated_count}
                </span>
              </div>
              <div className="counter-box">
                <span className="counter-label">YouTube Enriched</span>
                <span className="counter-value">
                  {currentDisplayRun.youtube_processed_count ?? 0}
                </span>
              </div>
            </div>

            {/* Error summary if present */}
            {currentDisplayRun.error_summary && (
              <div
                style={{
                  marginTop: '1rem',
                  padding: '0.75rem 1rem',
                  backgroundColor: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.25)',
                  borderRadius: '6px',
                  color: '#fca5a5',
                  fontSize: '0.85rem',
                }}
              >
                <strong>Error Summary: </strong>
                {currentDisplayRun.error_summary}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Realtime Event Timeline */}
      <div className="section-card" style={{ marginTop: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>
              {selectedRun ? `Event Timeline (Run #${selectedRun.id})` : 'Realtime Event Timeline'}
            </h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              {selectedRun
                ? `Showing historical events for Run #${selectedRun.id}`
                : 'Append-only durable event stream delivered via SSE'}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            {selectedRun && (
              <button
                className="order-btn"
                style={{ fontSize: '0.8rem', padding: '0.25rem 0.5rem' }}
                onClick={() => {
                  setSelectedRun(null);
                  if (activeRun?.events) setEvents(activeRun.events);
                }}
              >
                Reset to Live
              </button>
            )}
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              {events.length} events recorded
            </span>
          </div>
        </div>

        {events.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', fontStyle: 'italic', padding: '1rem 0' }}>
            No events in timeline yet. Events will appear automatically when pipeline executes.
          </p>
        ) : (
          <div className="timeline-list">
            {[...events].reverse().map((ev) => (
              <div key={ev.id} className="timeline-item">
                <span className="timeline-time">
                  {new Date(ev.created_at).toISOString().substring(11, 19)}
                </span>
                <span className="stage-pill">{ev.stage}</span>
                <div className="timeline-message">
                  <div>{ev.message}</div>
                  {ev.payload && (
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem', fontFamily: 'monospace' }}>
                      {JSON.stringify(ev.payload)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Historical Runs Table */}
      <div className="section-card" style={{ marginTop: '2rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>Run History</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1rem' }}>
          Durable history of the past 20 scheduled and manual runs
        </p>

        {runs.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', fontStyle: 'italic' }}>
            No execution history found.
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="run-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Trigger</th>
                  <th>Status</th>
                  <th>Processed / Target</th>
                  <th>Reviews</th>
                  <th>Summaries</th>
                  <th>Embeddings</th>
                  <th>Started At</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <strong>#{r.id}</strong>
                    </td>
                    <td>
                      <span style={{ textTransform: 'capitalize' }}>{r.trigger_type}</span>
                    </td>
                    <td>
                      <span
                        className={`status-badge ${
                          r.status === 'completed'
                            ? 'ok'
                            : r.status === 'running'
                            ? 'info'
                            : r.status === 'partial'
                            ? 'warning'
                            : 'down'
                        }`}
                        style={{ fontSize: '0.75rem', padding: '0.15rem 0.5rem' }}
                      >
                        ● {r.status}
                      </span>
                    </td>
                    <td>
                      {r.processed_count} / {r.target_count}
                      {r.failed_count > 0 && (
                        <span style={{ color: '#f87171', marginLeft: '0.4rem', fontSize: '0.8rem' }}>
                          ({r.failed_count} failed)
                        </span>
                      )}
                    </td>
                    <td>{r.reviews_processed_count}</td>
                    <td>{r.summaries_generated_count}</td>
                    <td>{r.embeddings_generated_count}</td>
                    <td>{new Date(r.created_at).toUTCString().substring(0, 22)}</td>
                    <td>
                      <button
                        className="order-btn"
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
                        onClick={() => {
                          setSelectedRun(r);
                          if (r.events && r.events.length > 0) {
                            setEvents(r.events);
                          }
                        }}
                      >
                        View Events
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
