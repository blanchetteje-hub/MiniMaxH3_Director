import { useCallback, useEffect, useState } from 'react'
import { invokeBridge } from '../lib/pywebview.js'

export default function Configuration({ onSettingsLoaded }) {
  const [settings, setSettings] = useState(null)
  const [error, setError] = useState('')
  const [newImageName, setNewImageName] = useState('')

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const loaded = await invokeBridge('get_settings')
        setSettings(loaded)
        if (onSettingsLoaded) {
          onSettingsLoaded(loaded)
        }
      } catch (err) {
        setError(`Failed to load settings: ${err.message}`)
      }
    }
    loadSettings()
  }, [onSettingsLoaded])

  const saveSettings = useCallback(
    async (updatedSettings) => {
      try {
        const result = await invokeBridge('save_settings', updatedSettings)
        if (!result.ok) {
          setError(result.error)
        } else {
          setError('')
        }
      } catch (err) {
        setError(`Failed to save settings: ${err.message}`)
      }
    },
    [],
  )

  const updateComfyUIUrl = (url) => {
    const updated = { ...settings, comfyui_url: url }
    setSettings(updated)
    saveSettings({ comfyui_url: url })
  }

  const updateLMStudioUrl = (url) => {
    const updated = { ...settings, lm_studio_url: url }
    setSettings(updated)
    saveSettings({ lm_studio_url: url })
  }

  const addImage = () => {
    if (!newImageName.trim()) {
      setError('Image name cannot be empty.')
      return
    }
    const updated = {
      ...settings,
      defined_images: [...settings.defined_images, newImageName.trim()],
    }
    setSettings(updated)
    setNewImageName('')
    saveSettings({ defined_images: updated.defined_images })
  }

  const removeImage = (index) => {
    const updated = {
      ...settings,
      defined_images: settings.defined_images.filter((_, i) => i !== index),
    }
    setSettings(updated)
    saveSettings({ defined_images: updated.defined_images })
  }

  if (!settings) {
    return <div className="panel config-panel loading">Loading configuration...</div>
  }

  return (
    <section className="panel config-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">System configuration</p>
          <h2>External Services & Resources</h2>
        </div>
      </div>

      <div className="config-section">
        <label className="field">
          <span>ComfyUI URL</span>
          <input
            type="url"
            value={settings.comfyui_url}
            onChange={(e) => updateComfyUIUrl(e.target.value)}
            placeholder="http://127.0.0.1:8188"
          />
          <small>Address of your ComfyUI server. Updates all 3 workflows.</small>
        </label>

        <label className="field">
          <span>LM Studio URL</span>
          <input
            type="url"
            value={settings.lm_studio_url}
            onChange={(e) => updateLMStudioUrl(e.target.value)}
            placeholder="http://127.0.0.1:1234"
          />
          <small>Address of your LM Studio server.</small>
        </label>
      </div>

      <div className="config-section">
        <div className="subheading-row">
          <div>
            <h3>Defined Images</h3>
            <p>Reference images for generation workflows (unlimited).</p>
          </div>
        </div>

        {settings.defined_images.length > 0 && (
          <div className="images-list">
            {settings.defined_images.map((image, index) => (
              <div className="image-item" key={index}>
                <span>{image}</span>
                <button
                  className="icon-button delete"
                  type="button"
                  aria-label={`Remove ${image}`}
                  onClick={() => removeImage(index)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="add-image-row">
          <input
            type="text"
            value={newImageName}
            onChange={(e) => setNewImageName(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                addImage()
              }
            }}
            placeholder="e.g., hero_shot.jpg or reference_frame"
            aria-label="New image name or path"
          />
          <button className="secondary-button compact" type="button" onClick={addImage}>
            + Add Image
          </button>
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}
    </section>
  )
}
