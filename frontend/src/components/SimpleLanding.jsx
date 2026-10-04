import { useEffect, useState } from 'react'
import { invokeBridge } from '../lib/pywebview.js'

const defaults = {
  vram_mode: '32', segment_length: '8', total_segments: '5', megapixels: '0.5',
  comfyui_url: 'http://127.0.0.1:8188', llm_host_url: 'http://127.0.0.1:1234',
}

export default function SimpleLanding({ disabled, onGenerate }) {
  const [settings, setSettings] = useState(defaults)
  const [files, setFiles] = useState({ story: '', subjects: '' })
  const [saved, setSaved] = useState({ story: '', subjects: '' })
  const [message, setMessage] = useState('')
  const [images, setImages] = useState([])

  useEffect(() => {
    invokeBridge('get_settings').then(savedSettings => setSettings(current => ({
      ...current,
      ...Object.fromEntries(Object.keys(defaults).filter(key => savedSettings[key] != null).map(key => [key, String(savedSettings[key])])),
    }))).catch(() => {})
    Promise.all(['story', 'subjects'].map(key => invokeBridge('read_file', key))).then(results => {
      const values = Object.fromEntries(['story', 'subjects'].map((key, i) => [key, results[i].content]))
      setFiles(values)
      setSaved(values)
    }).catch(error => setMessage(error.message))
    let active = true
    const refreshImages = () => invokeBridge('get_output_images')
      .then(result => active && setImages(result))
      .catch(() => {})
    refreshImages()
    const timer = window.setInterval(refreshImages, 3000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  const update = (key, value) => {
    setSettings(current => ({ ...current, [key]: value }))
    invokeBridge('save_settings', { [key]: value }).catch(() => {})
  }
  const updateFile = (key, content) => setFiles(current => ({ ...current, [key]: content }))
  const saveFiles = async () => {
    setMessage('Saving…')
    try {
      for (const key of ['story', 'subjects']) {
        if (files[key] !== saved[key]) {
          const result = await invokeBridge('save_file', key, files[key])
          if (!result.ok) throw new Error(result.error)
        }
      }
      setSaved(files)
      setMessage('Saved')
    } catch (error) { setMessage(error.message) }
  }
  const generate = async (mode, action) => {
    try {
      for (const key of ['story', 'subjects']) {
        if (files[key] !== saved[key]) {
          const result = await invokeBridge('save_file', key, files[key])
          if (!result.ok) throw new Error(result.error)
        }
      }
      setSaved(files)
      setMessage('')
      await onGenerate({ ...settings, generation_mode: 'new', vram_mode: mode, action, resume: '1', loras: [] })
    } catch (error) { setMessage(error.message) }
  }

  return <section className="panel settings-panel simple-panel">
    <div className="panel-heading"><div><p className="eyebrow">Quick start</p><h2>Create your video</h2></div></div>
    <div className="simple-fields">
      <label className="field"><span className="field-label">Segment length (seconds)</span><input type="number" min="0.01" step="any" value={settings.segment_length} disabled={disabled} onChange={event => update('segment_length', event.target.value)} /></label>
      <label className="field"><span className="field-label">Total segments</span><input type="number" min="1" step="1" value={settings.total_segments} disabled={disabled} onChange={event => update('total_segments', event.target.value)} /></label>
      <label className="field"><span className="field-label">Quality (megapixels)</span><input type="number" min="0.01" step="any" value={settings.megapixels} disabled={disabled} onChange={event => update('megapixels', event.target.value)} /></label>
      <label className="field"><span className="field-label">ComfyUI URL</span><input type="url" value={settings.comfyui_url} placeholder="http://127.0.0.1:8188" disabled={disabled} onChange={event => update('comfyui_url', event.target.value)} /></label>
      <label className="field"><span className="field-label">LLM URL</span><input type="url" value={settings.llm_host_url} placeholder="http://127.0.0.1:1234" disabled={disabled} onChange={event => update('llm_host_url', event.target.value)} /></label>
    </div>
    <p className="muted-note">Video always renders in 16:9.</p>
    {['story', 'subjects'].map(key => <label className="field simple-file" key={key}><span className="field-label">{key === 'story' ? 'Story' : 'Subjects'}</span><textarea aria-label={key === 'story' ? 'Story' : 'Subjects'} value={files[key]} disabled={disabled} onChange={event => updateFile(key, event.target.value)} /></label>)}
    <div className="generation-actions simple-actions">
      <button type="button" className="secondary-button generate-button" disabled={disabled} onClick={() => generate('16', 'prompts')}>16 GB · Generate Prompts</button>
      <button type="button" className="secondary-button generate-button" disabled={disabled} onClick={() => generate('16', 'render')}>16 GB · Generate Video</button>
      <button type="button" className="primary-button generate-button" disabled={disabled} onClick={() => generate('32', 'generate')}>32+ GB · Generate</button>
    </div>
    <div className="editor-footer"><span className="editor-message" role="status">{message}</span><button type="button" className="secondary-button" onClick={saveFiles} disabled={disabled || (files.story === saved.story && files.subjects === saved.subjects)}>Save story and subjects</button></div>
    <section className="simple-image-gallery" aria-label="Generated images">
      <div className="panel-heading"><div><p className="eyebrow">Output</p><h2>Generated images</h2></div><span className="muted-note">Latest images in the video output folder</span></div>
      {images.length ? <div className="simple-image-grid">{images.map(image => <figure className="simple-image-card" key={`${image.name}-${image.modified_at}`}><img src={image.src} alt={image.name} loading="lazy" /><figcaption title={image.name}>{image.name}</figcaption></figure>)}</div> : <p className="muted-note">No generated images yet.</p>}
    </section>
  </section>
}
