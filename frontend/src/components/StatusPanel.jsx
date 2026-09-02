function formatTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

export default function StatusPanel({ bridgeState, status, onStop }) {
  const state = status?.state || 'idle'
  const running = Boolean(status?.running)

  return (
    <section className={`panel status-panel state-${state}`}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Runtime</p>
          <h2>Status</h2>
        </div>
        <span className={`status-pill state-${state}`}>
          <i /> {state}
        </span>
      </div>

      <div className="status-message">{status?.message || 'Ready'}</div>
      <dl className="status-details">
        <div>
          <dt>Desktop bridge</dt>
          <dd className={bridgeState === 'ready' ? 'good' : 'muted'}>{bridgeState}</dd>
        </div>
        <div>
          <dt>Process ID</dt>
          <dd>{status?.pid || '—'}</dd>
        </div>
        <div>
          <dt>Segment</dt>
          <dd>
            {status?.current_segment
              ? `${status.current_segment}${status.total_segments ? ` / ${status.total_segments}` : ''}`
              : '—'}
          </dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{formatTime(status?.started_at)}</dd>
        </div>
        <div>
          <dt>Exit code</dt>
          <dd>{status?.return_code ?? '—'}</dd>
        </div>
      </dl>

      {status?.command_display && (
        <div className="command-preview">
          <span>Command</span>
          <code>{status.command_display}</code>
        </div>
      )}

      <button
        className="danger-button stop-button"
        type="button"
        onClick={onStop}
        disabled={!running || state === 'stopping'}
      >
        <span>■</span> {state === 'stopping' ? 'Stopping…' : 'Stop generation'}
      </button>
      <p className="stop-note">
        Stop sends the engine’s emergency interrupt. Remote ComfyUI work already queued may
        need separate cancellation in ComfyUI.
      </p>
    </section>
  )
}
