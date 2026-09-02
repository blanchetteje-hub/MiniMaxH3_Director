import { useEffect, useRef, useState } from 'react'

export default function LogViewer({ output, state, onClear }) {
  const viewerRef = useRef(null)
  const [following, setFollowing] = useState(true)

  useEffect(() => {
    const viewer = viewerRef.current
    if (viewer && following) viewer.scrollTop = viewer.scrollHeight
  }, [output, following])

  const handleScroll = () => {
    const viewer = viewerRef.current
    if (!viewer) return
    const distance = viewer.scrollHeight - viewer.scrollTop - viewer.clientHeight
    setFollowing(distance < 28)
  }

  return (
    <section className="panel log-panel">
      <div className="panel-heading log-heading">
        <div>
          <p className="eyebrow">stdout + stderr</p>
          <h2>Live output</h2>
        </div>
        <div className="log-actions">
          {!following && (
            <button className="text-button" type="button" onClick={() => setFollowing(true)}>
              Jump to latest
            </button>
          )}
          <button className="secondary-button compact" type="button" onClick={onClear}>
            Clear log
          </button>
        </div>
      </div>
      <div className={`console state-${state}`} ref={viewerRef} onScroll={handleScroll}>
        <pre>{output || 'Waiting for generation output…'}</pre>
      </div>
    </section>
  )
}
