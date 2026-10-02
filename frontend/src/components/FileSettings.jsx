import { useEffect, useMemo, useState } from 'react'
import { invokeBridge } from '../lib/pywebview.js'
import HelpTip from './HelpTip.jsx'

const FILE_HELP = {
  story: 'The source story used by New to create the story arc and beats.',
  beats: 'Ordered story events used by Existing. New replaces these with beats generated from the story.',
  subjects: 'Stable subject identities and reference Picture mappings supplied to the Director.',
  canonical_data: 'Optional canonical character facts used by planning. The LLM still generates character canon from the story and subjects when this is missing or blank. Its contents are appended verbatim to segment 1 subject definitions when present.',
  phrase_exclusions: 'One excluded word or phrase per line, supplied to planning and checked in beats.',
  generated_prompts: 'Saved final video prompts and render settings. Render-Only reads this package without calling the LLM.',
  generation_state: 'Read-only checkpoint with completed clips and continuity state, used for resume and repair.',
  story_arc: 'Read-only macro story plan generated from the story.',
  initial_workflow: 'Read-only ComfyUI workflow used to render the opening clip.',
  append_workflow: 'Read-only ComfyUI workflow that extends the preceding clip.',
  refresh_workflow: 'Read-only ComfyUI workflow used at scene refresh boundaries.',
  repair_workflow: 'Read-only ComfyUI workflow used to rerender a middle clip using its neighboring clips.',
}


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
          <h2>Files & configuration <HelpTip text="Review and edit project source files here. Changes are written only when you select Save file. Editing is disabled while generation runs." /></h2>
        </div>
        <span className="muted-note">Fixed paths used by minimax.py</span>
      </div>
      <div className="file-workspace">
        <nav className="file-list" aria-label="Project files">
          {files.map((file) => (
            <div key={file.key} className="file-option">
              <button
                type="button"
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
              <HelpTip text={FILE_HELP[file.key] || `Review ${file.label}. ${file.editable ? 'Editable source file; save changes before generation.' : 'Read-only generated or workflow file.'}`} />
            </div>
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
