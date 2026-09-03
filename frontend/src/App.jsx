import { useCallback, useEffect, useRef, useState } from 'react'
import Configuration from './components/Configuration.jsx'
import FileSettings from './components/FileSettings.jsx'
import GenerationForm from './components/GenerationForm.jsx'
import LogViewer from './components/LogViewer.jsx'
import StatusPanel from './components/StatusPanel.jsx'
import { invokeBridge, waitForBridge } from './lib/pywebview.js'

const IDLE_STATUS = {
  state: 'idle',
  message: 'Ready',
  running: false,
  pid: null,
  return_code: null,
}

export default function App() {
  const [bridgeState, setBridgeState] = useState('connecting')
  const [bridgeError, setBridgeError] = useState('')
  const [status, setStatus] = useState(IDLE_STATUS)
  const [logOutput, setLogOutput] = useState('')
  const [files, setFiles] = useState([])
  const logOffset = useRef(0)

  const refreshFiles = useCallback(async () => {
    if (bridgeState !== 'ready') return
    setFiles(await invokeBridge('get_file_settings'))
  }, [bridgeState])

  useEffect(() => {
    let active = true
    waitForBridge()
      .then(() => {
        if (!active) return
        setBridgeState('ready')
        setBridgeError('')
      })
      .catch((error) => {
        if (!active) return
        setBridgeState('unavailable')
        setBridgeError(error.message)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (bridgeState !== 'ready') return
    let active = true

    const pollStatus = async () => {
      try {
        const nextStatus = await invokeBridge('get_status')
        if (active) setStatus(nextStatus)
      } catch (error) {
        if (active) setBridgeError(error.message)
      }
    }
    const pollLog = async () => {
      try {
        const update = await invokeBridge('get_log_output', logOffset.current)
        if (!active) return
        if (update.text) setLogOutput((current) => current + update.text)
        logOffset.current = update.next_offset
      } catch (error) {
        if (active) setBridgeError(error.message)
      }
    }

    pollStatus()
    pollLog()
    invokeBridge('get_file_settings')
      .then((result) => active && setFiles(result))
      .catch((error) => active && setBridgeError(error.message))
    const statusTimer = window.setInterval(pollStatus, 700)
    const logTimer = window.setInterval(pollLog, 300)
    return () => {
      active = false
      window.clearInterval(statusTimer)
      window.clearInterval(logTimer)
    }
  }, [bridgeState])

  const startGeneration = async (settings) => {
    try {
      const result = await invokeBridge('start_generation', settings)
      setStatus(result.status)
      if (!result.ok) setBridgeError(result.error)
      else setBridgeError('')
    } catch (error) {
      setBridgeError(error.message)
    }
  }

  const stopGeneration = async () => {
    try {
      const result = await invokeBridge('stop_generation')
      setStatus(result.status)
    } catch (error) {
      setBridgeError(error.message)
    }
  }

  const clearLog = async () => {
    try {
      await invokeBridge('clear_log_output')
      logOffset.current = 0
      setLogOutput('')
    } catch (error) {
      setBridgeError(error.message)
    }
  }

  const running = Boolean(status.running)
  const ready = bridgeState === 'ready'

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-mark">H3</div>
        <div>
          <h1>MiniMax H3</h1>
          <p>Continuous video automation</p>
        </div>
        <div className="header-state">
          <span className={ready ? 'connection-dot online' : 'connection-dot'} />
          {ready ? 'Desktop connected' : 'Bridge unavailable'}
        </div>
      </header>

      {bridgeError && <div className="bridge-banner">{bridgeError}</div>}

      <main>
        <Configuration />
        <div className="dashboard-grid">
          <GenerationForm disabled={!ready || running} onGenerate={startGeneration} />
          <StatusPanel bridgeState={bridgeState} status={status} onStop={stopGeneration} />
        </div>
        <LogViewer output={logOutput} state={status.state} onClear={clearLog} />
        <FileSettings
          files={files}
          running={running}
          bridgeReady={ready}
          onFilesChanged={refreshFiles}
        />
      </main>
    </div>
  )
}
