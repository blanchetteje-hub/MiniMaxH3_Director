import { useEffect, useMemo, useState } from 'react'
import { invokeBridge } from '../lib/pywebview.js'

export default function FileSettings({ files, running, bridgeReady, onFilesChanged }) {
  const [selectedKey, setSelectedKey] = useState('story')
  const [content, setContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [message, setMessage] = useState('')
  const selected = useMemo(
    () => files.find((file) => file.key === selectedKey),
    [files, selectedKey],
  )

  useEffect(() => {
    if (!bridgeReady || !selectedKey) return
    let active = true
    setMessage('Loading…')
    invokeBridge('read_file', selectedKey)
      .then((result) => {
        if (!active) return
        setContent(result.content)
        setSavedContent(result.content)
        setMessage(result.exists ? '' : 'This file does not exist yet. Saving will create it.')
      })
      .catch((error) => active && setMessage(error.message))
    return () => {
      active = false
    }
  }, [bridgeReady, selectedKey])

  const save = async () => {
    setMessage('Saving…')
    try {
      const result = await invokeBridge('save_file', selectedKey, content)
      if (!result.ok) throw new Error(result.error)
      setSavedContent(content)
      setMessage('Saved')
      onFilesChanged()
    } catch (error) {
      setMessage(error.message)
    }
  }

  return (
    <section className="panel files-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Project sources</p>
          <h2>Files & configuration</h2>
        </div>
        <span className="muted-note">Fixed paths used by minimax.py</span>
      </div>
      <div className="file-workspace">
        <nav className="file-list" aria-label="Project files">
          {files.map((file) => (
            <button
              type="button"
              key={file.key}
              className={selectedKey === file.key ? 'file-item selected' : 'file-item'}
              onClick={() => setSelectedKey(file.key)}
            >
              <i className={file.exists ? 'exists' : ''} />
              <span>
                <strong>{file.label}</strong>
                <small>{file.exists ? `${file.size.toLocaleString()} bytes` : 'Missing'}</small>
              </span>
              {!file.editable && <em>read only</em>}
            </button>
          ))}
        </nav>
        <div className="file-editor">
          <div className="file-path" title={selected?.path}>{selected?.path || 'No file selected'}</div>
          <textarea
            aria-label={`${selected?.label || 'File'} content`}
            value={content}
            onChange={(event) => setContent(event.target.value)}
            readOnly={!selected?.editable || running}
            spellCheck="false"
          />
          <div className="editor-footer">
            <span className="editor-message">{message}</span>
            {selected?.editable && (
              <button
                className="secondary-button"
                type="button"
                onClick={save}
                disabled={running || content === savedContent || !bridgeReady}
              >
                Save file
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
