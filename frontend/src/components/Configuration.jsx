import { useCallback, useEffect, useState } from 'react'
import { invokeBridge } from '../lib/pywebview.js'
import HelpTip from './HelpTip.jsx'

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

  const updateLLMHostUrl = (url) => {
    const updated = { ...settings, llm_host_url: url }
    setSettings(updated)
    saveSettings({ llm_host_url: url })
  }

  const updateLoraDir = (dir) => {
    const updated = { ...settings, lora_dir: dir }
    setSettings(updated)
    saveSettings({ lora_dir: dir })
  }

  const addImage = () => {
    if (!newImageName.trim()) {
      setError('Image name cannot be empty.')
      return
    }
    if (settings.defined_images.length >= 6) {
      setError('At most six reference images can be defined.')
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

      <details className="advanced" open>
        <summary>Service connections & LoRA directory</summary>
        <div className="config-section">
        <div className="field">
          <span>ComfyUI URL <HelpTip text="Address of the ComfyUI server that renders your video. Start this service before rendering." /></span>
          <input
            type="url"
            aria-label="ComfyUI URL"
            value={settings.comfyui_url}
            onChange={(e) => updateComfyUIUrl(e.target.value)}
            placeholder="http://127.0.0.1:8188"
          />
          <small>Address of your ComfyUI server, used by all workflows.</small>
        </div>

        <div className="field">
          <span>LLM host URL <HelpTip text="Address of the local language model API used to plan beats and write video prompts." /></span>
          <input
            type="url"
            aria-label="LLM host URL"
            value={settings.llm_host_url}
            onChange={(e) => updateLLMHostUrl(e.target.value)}
            placeholder="http://127.0.0.1:1234"
          />
          <small>Address of your LLM host server.</small>
        </div>
        <div className="field">
          <span>LoRA Path <HelpTip text="Folder containing the LoRA files named in global settings or beats. Paths must be accessible to the generator." /></span>
          <input
            type="text"
            aria-label="LoRA Path"
            value={settings.lora_dir}
            onChange={(e) => updateLoraDir(e.target.value)}
            placeholder="/mnt/h/StableDiffusion/loras"
          />
          <small>Directory containing LoRA files.</small>
        </div>
        </div>
      </details>

      <details className="advanced">
        <summary>Defined Images (optional)</summary>
        <div className="config-section">
        <div className="subheading-row">
          <div>
            <h3>Defined Images <HelpTip text="Up to six ComfyUI input filenames or paths, in order. These become Picture 1 through Picture 6 and override the corresponding workflow reference images." /></h3>
            <p>Up to six ordered reference images for all generation workflows.</p>
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
          <HelpTip text="Enter a reference image filename or path, then select Add Image. Remove an image with its × button; list order determines its Picture number." />
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
      </details>

      {error && <p className="form-error">{error}</p>}
    </section>
  )
}
