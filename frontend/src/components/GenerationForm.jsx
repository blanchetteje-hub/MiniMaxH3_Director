import { useMemo, useState, useEffect, useCallback } from 'react'
import { invokeBridge } from '../lib/pywebview.js'

const INITIAL_SETTINGS = {
  segment_length: '',
  total_length: '',
  megapixels: '',
  resume: '1',
  steps: '6',
  context_frames: '7',
  refresh: '6',
  vision_continuity: '1',
  dino_skip: false,
  disable_onnx_dino: false,
  dino_confidence: '0.80',
  dino_box_threshold: '0.35',
  dino_text_threshold: '0.25',
  dino_frame_interval: '8',
  dino_max_candidates: '12',
  dino_max_state_age: '1.0',
  dino_crop_padding_x: '0.12',
  dino_crop_padding_y: '0.12',
  dino_min_bbox_area_ratio: '0.01',
  identity_confidence: '0.48',
  identity_margin: '0.05',
  repair: '',
  model: 'ministral',
  first_frame: false,
  loras: [],
  beat_count: '',
  lora_dir: '',
}

function NumberField({ label, help, ...props }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type="number" {...props} />
      {help && <small>{help}</small>}
    </label>
  )
}

export default function GenerationForm({ disabled, onGenerate, onGenerateStory }) {
  const [settings, setSettings] = useState(INITIAL_SETTINGS)
  const [mode, setMode] = useState('new')
  const [error, setError] = useState('')

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const savedSettings = await invokeBridge('get_settings')
        setSettings((current) => ({
          ...current,
          segment_length: savedSettings.segment_length ?? current.segment_length,
          total_length: savedSettings.total_length ?? current.total_length,
          megapixels: savedSettings.megapixels ?? current.megapixels,
          resume: savedSettings.resume ?? current.resume,
          steps: savedSettings.steps ?? current.steps,
          context_frames: savedSettings.context_frames ?? current.context_frames,
          refresh: savedSettings.refresh ?? current.refresh,
          vision_continuity: savedSettings.vision_continuity ?? current.vision_continuity,
          dino_skip: savedSettings.dino_skip ?? current.dino_skip,
          disable_onnx_dino: savedSettings.disable_onnx_dino ?? current.disable_onnx_dino,
          dino_confidence: savedSettings.dino_confidence ?? current.dino_confidence,
          dino_box_threshold: savedSettings.dino_box_threshold ?? current.dino_box_threshold,
          dino_text_threshold: savedSettings.dino_text_threshold ?? current.dino_text_threshold,
          dino_frame_interval: savedSettings.dino_frame_interval ?? current.dino_frame_interval,
          dino_max_candidates: savedSettings.dino_max_candidates ?? current.dino_max_candidates,
          dino_max_state_age: savedSettings.dino_max_state_age ?? current.dino_max_state_age,
          dino_crop_padding_x: savedSettings.dino_crop_padding_x ?? current.dino_crop_padding_x,
          dino_crop_padding_y: savedSettings.dino_crop_padding_y ?? current.dino_crop_padding_y,
          dino_min_bbox_area_ratio: savedSettings.dino_min_bbox_area_ratio ?? current.dino_min_bbox_area_ratio,
          identity_confidence: savedSettings.identity_confidence ?? current.identity_confidence,
          identity_margin: savedSettings.identity_margin ?? current.identity_margin,
          repair: savedSettings.repair ?? current.repair,
          model: savedSettings.model ?? current.model,
          first_frame: savedSettings.first_frame ?? current.first_frame,
          loras: Array.isArray(savedSettings.loras) ? savedSettings.loras : current.loras,
          beat_count: savedSettings.beat_count ?? current.beat_count,
          lora_dir: savedSettings.lora_dir ?? current.lora_dir,
        }))
      } catch (err) {
        // Silently fall back to defaults if settings can't be loaded
      }
    }
    loadSettings()
  }, [])

  const saveSettings = useCallback(
    async (updatedSettings) => {
      try {
        await invokeBridge('save_settings', updatedSettings)
      } catch (err) {
        // Silently ignore save errors - user can still generate
      }
    },
    [],
  )

  const totalSegments = useMemo(() => {
    const segment = Number(settings.segment_length)
    const total = Number(settings.total_length)
    return segment > 0 && total > 0 ? Math.ceil(total / segment) : null
  }, [settings.segment_length, settings.total_length])

  const setField = (field, value) => {
    setSettings((current) => {
      const updated = { ...current, [field]: value }
      saveSettings({ [field]: value })
      return updated
    })
  }

  const changeMode = (nextMode) => {
    setMode(nextMode)
    setSettings((current) => {
      const updated = {
        ...current,
        resume: nextMode === 'resume' ? current.resume : '1',
        repair: nextMode === 'repair' ? current.repair : '',
      }
      saveSettings({ resume: updated.resume, repair: updated.repair })
      return updated
    })
  }

  const updateLora = (index, field, value) => {
    setSettings((current) => {
      const updated = {
        ...current,
        loras: current.loras.map((lora, itemIndex) =>
          itemIndex === index ? { ...lora, [field]: value } : lora,
        ),
      }
      saveSettings({ loras: updated.loras })
      return updated
    })
  }

  const submit = (event) => {
    event.preventDefault()
    setError('')
    const positiveFields = [
      ['segment_length', 'Segment duration'],
      ['total_length', 'Total duration'],
      ['megapixels', 'Megapixels'],
      ['steps', 'Steps'],
      ['context_frames', 'Context frames'],
      ['refresh', 'Refresh interval'],
    ]
    const invalid = positiveFields.find(([key]) => !(Number(settings[key]) > 0))
    if (invalid) {
      setError(`${invalid[1]} must be greater than zero.`)
      return
    }
    if (settings.vision_continuity === '' || !/^\d+$/.test(settings.vision_continuity)) {
      setError('Continuity cadence must be a whole number (0 disables it).')
      return
    }
    const dinoRatioFields = [
      ['dino_confidence', 'DINO confidence'],
      ['dino_box_threshold', 'DINO box threshold'],
      ['dino_text_threshold', 'DINO text threshold'],
      ['dino_crop_padding_x', 'DINO horizontal crop padding'],
      ['dino_crop_padding_y', 'DINO vertical crop padding'],
      ['dino_min_bbox_area_ratio', 'DINO minimum bbox area ratio'],
    ]
    const invalidDinoRatio = dinoRatioFields.find(
      ([key]) => settings[key] === '' || !(Number(settings[key]) >= 0 && Number(settings[key]) <= 1),
    )
    if (invalidDinoRatio) {
      setError(`${invalidDinoRatio[1]} must be between 0 and 1.`)
      return
    }
    if (
      settings.identity_confidence === ''
      || !(Number(settings.identity_confidence) >= -1 && Number(settings.identity_confidence) <= 1)
    ) {
      setError('Identity confidence must be between -1 and 1.')
      return
    }
    if (
      settings.identity_margin === ''
      || !(Number(settings.identity_margin) >= 0 && Number(settings.identity_margin) <= 2)
    ) {
      setError('Identity margin must be between 0 and 2.')
      return
    }
    const dinoIntegerFields = [
      ['dino_frame_interval', 'DINO frame interval'],
      ['dino_max_candidates', 'DINO maximum candidates'],
    ]
    const invalidDinoInteger = dinoIntegerFields.find(
      ([key]) => !/^\d+$/.test(settings[key]) || Number(settings[key]) <= 0,
    )
    if (invalidDinoInteger) {
      setError(`${invalidDinoInteger[1]} must be a whole number greater than zero.`)
      return
    }
    if (settings.dino_max_state_age === '' || !(Number(settings.dino_max_state_age) > 0)) {
      setError('DINO maximum rendered-state age must be greater than zero.')
      return
    }
    if (mode === 'resume' && !(Number(settings.resume) > 0)) {
      setError('Resume segment must be greater than zero.')
      return
    }
    if (mode === 'repair' && !(Number(settings.repair) > 1)) {
      setError('Repair must target a middle segment after segment 1.')
      return
    }
    if (settings.loras.some((lora) => !lora.name.trim() || lora.strength === '')) {
      setError('Each LoRA needs both a name and a strength.')
      return
    }
    onGenerate({
      ...settings,
      resume: mode === 'resume' ? settings.resume : '1',
      repair: mode === 'repair' ? settings.repair : null,
    })
  }

  const generateStory = async () => {
    setError('')
    const beatCount = Number(settings.beat_count)
    if (!(beatCount > 0) || !Number.isInteger(beatCount)) {
      setError('Story beats must be a whole number greater than zero.')
      return
    }
    const result = await onGenerateStory(settings)
    if (result && !result.ok) setError(result.error)
  }

  return (
    <section className="panel settings-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Pipeline input</p>
          <h2>Generation settings</h2>
        </div>
        {totalSegments && (
          <span className="calculated">{totalSegments} segments</span>
        )}
      </div>

      <form onSubmit={submit}>
        <div className="field-grid primary-fields">
          <NumberField
            label="Segment duration"
            help="Seconds per generated clip"
            value={settings.segment_length}
            onChange={(event) => setField('segment_length', event.target.value)}
            placeholder="5"
            min="0.01"
            step="any"
            required
            disabled={disabled}
          />
          <NumberField
            label="Total duration"
            help="Full story length in seconds"
            value={settings.total_length}
            onChange={(event) => setField('total_length', event.target.value)}
            placeholder="60"
            min="0.01"
            step="any"
            required
            disabled={disabled}
          />
          <NumberField
            label="Megapixels"
            help="Initial and refresh target"
            value={settings.megapixels}
            onChange={(event) => setField('megapixels', event.target.value)}
            placeholder="0.5"
            min="0.01"
            step="any"
            required
            disabled={disabled}
          />
        </div>

        <div className="mode-group" role="group" aria-label="Generation mode">
          {[
            ['new', 'New run'],
            ['resume', 'Resume'],
            ['repair', 'Repair'],
          ].map(([value, label]) => (
            <button
              className={mode === value ? 'mode-button selected' : 'mode-button'}
              type="button"
              key={value}
              onClick={() => changeMode(value)}
              disabled={disabled}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === 'resume' && (
          <div className="inline-callout">
            <NumberField
              label="Resume at segment"
              help="Prior segments must exist in generation_state.json"
              value={settings.resume}
              onChange={(event) => setField('resume', event.target.value)}
              min="1"
              step="1"
              disabled={disabled}
            />
          </div>
        )}
        {mode === 'repair' && (
          <div className="inline-callout warning">
            <NumberField
              label="Repair segment"
              help="Uses duration and resolution from the checkpoint; the target must have clips on both sides."
              value={settings.repair}
              onChange={(event) => setField('repair', event.target.value)}
              min="2"
              step="1"
              disabled={disabled}
            />
          </div>
        )}

        <details className="advanced" open>
          <summary>Pipeline controls</summary>
          <div className="field-grid">
            <NumberField
              label="Steps"
              value={settings.steps}
              onChange={(event) => setField('steps', event.target.value)}
              min="1"
              step="1"
              disabled={disabled}
            />
            <NumberField
              label="Context frames"
              help="Engine default: 7"
              value={settings.context_frames}
              onChange={(event) => setField('context_frames', event.target.value)}
              min="1"
              step="1"
              disabled={disabled}
            />
            <NumberField
              label="Refresh interval"
              help="Every Nth segment; engine default: 6"
              value={settings.refresh}
              onChange={(event) => setField('refresh', event.target.value)}
              min="1"
              step="1"
              disabled={disabled}
            />
            <NumberField
              label="Continuity cadence"
              help="DINO continuity cadence; 0 disables it, 1 checks every segment"
              value={settings.vision_continuity}
              onChange={(event) => setField('vision_continuity', event.target.value)}
              min="0"
              step="1"
              disabled={disabled}
            />
            <NumberField
              label="LoRA Path"
              help="Directory containing LoRA files (overrides default)"
              value={settings.lora_dir}
              onChange={(event) => setField('lora_dir', event.target.value)}
              disabled={disabled}
            />
            <label className="field">
              <span>Formatter</span>
              <select
                value={settings.model}
                onChange={(event) => setField('model', event.target.value)}
                disabled={disabled}
              >
                <option value="ministral">Ministral</option>
                <option value="qwen">Qwen</option>
              </select>
            </label>
          </div>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={settings.first_frame}
              onChange={(event) => setField('first_frame', event.target.checked)}
              disabled={disabled || mode === 'repair'}
            />
            <span>
              Add first-frame instructions to segment 1 <code>--ff</code>
            </span>
          </label>
        </details>

        <details className="advanced">
          <summary>Grounding DINO continuity</summary>
          <div className="field-grid">
            <NumberField
              label="Confidence"
              help="Minimum detection confidence; default: 0.80"
              value={settings.dino_confidence}
              onChange={(event) => setField('dino_confidence', event.target.value)}
              min="0"
              max="1"
              step="0.01"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Box threshold"
              help="Grounding DINO box threshold"
              value={settings.dino_box_threshold}
              onChange={(event) => setField('dino_box_threshold', event.target.value)}
              min="0"
              max="1"
              step="0.01"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Text threshold"
              help="Grounding DINO text threshold"
              value={settings.dino_text_threshold}
              onChange={(event) => setField('dino_text_threshold', event.target.value)}
              min="0"
              max="1"
              step="0.01"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Frame interval"
              help="Search backward every N frames"
              value={settings.dino_frame_interval}
              onChange={(event) => setField('dino_frame_interval', event.target.value)}
              min="1"
              step="1"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Maximum candidates"
              help="Maximum frames searched per subject"
              value={settings.dino_max_candidates}
              onChange={(event) => setField('dino_max_candidates', event.target.value)}
              min="1"
              step="1"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Maximum state age"
              help="Rendered-state search window at the segment end, in seconds"
              value={settings.dino_max_state_age}
              onChange={(event) => setField('dino_max_state_age', event.target.value)}
              min="0.01"
              step="0.1"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Horizontal padding"
              help="Proportional padding around the full bbox"
              value={settings.dino_crop_padding_x}
              onChange={(event) => setField('dino_crop_padding_x', event.target.value)}
              min="0"
              max="1"
              step="0.01"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Vertical padding"
              help="Proportional padding around the full bbox"
              value={settings.dino_crop_padding_y}
              onChange={(event) => setField('dino_crop_padding_y', event.target.value)}
              min="0"
              max="1"
              step="0.01"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Minimum bbox area"
              help="Minimum bbox area as a fraction of the frame"
              value={settings.dino_min_bbox_area_ratio}
              onChange={(event) => setField('dino_min_bbox_area_ratio', event.target.value)}
              min="0"
              max="1"
              step="0.001"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Identity confidence"
              help="ArcFace cosine threshold; default: 0.48"
              value={settings.identity_confidence}
              onChange={(event) => setField('identity_confidence', event.target.value)}
              min="-1"
              max="1"
              step="0.01"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
            <NumberField
              label="Identity margin"
              help="Minimum winner gap over the next candidate"
              value={settings.identity_margin}
              onChange={(event) => setField('identity_margin', event.target.value)}
              min="0"
              max="2"
              step="0.01"
              disabled={disabled || settings.dino_skip || settings.disable_onnx_dino}
            />
          </div>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={settings.dino_skip}
              onChange={(event) => setField('dino_skip', event.target.checked)}
              disabled={disabled}
            />
            <span>Skip Grounding DINO continuity detection (<code>--dino-skip</code>)</span>
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={settings.disable_onnx_dino}
              onChange={(event) => setField('disable_onnx_dino', event.target.checked)}
              disabled={disabled}
            />
            <span>
              Disable ONNX/DINO visual continuity (<code>--disable-onnx-dino</code>)
            </span>
          </label>
        </details>

        <div className="lora-section">
          <div className="subheading-row">
            <div>
              <h3>Global LoRAs</h3>
              <p>Applied in this order to every beat.</p>
            </div>
            <button
              className="secondary-button compact"
              type="button"
              onClick={() => {
                setSettings((current) => {
                  const updated = {
                    ...current,
                    loras: [...current.loras, { name: '', strength: '1' }],
                  }
                  saveSettings({ loras: updated.loras })
                  return updated
                })
              }}
              disabled={disabled}
            >
              + Add LoRA
            </button>
          </div>
          {settings.loras.map((lora, index) => (
            <div className="lora-row" key={index}>
              <input
                aria-label={`LoRA ${index + 1} name`}
                placeholder="filename.safetensors"
                value={lora.name}
                onChange={(event) => updateLora(index, 'name', event.target.value)}
                disabled={disabled}
              />
              <input
                aria-label={`LoRA ${index + 1} strength`}
                type="number"
                step="any"
                value={lora.strength}
                onChange={(event) => updateLora(index, 'strength', event.target.value)}
                disabled={disabled}
              />
              <button
                className="icon-button"
                type="button"
                aria-label={`Remove LoRA ${index + 1}`}
                onClick={() => {
                  setSettings((current) => {
                    const updated = {
                      ...current,
                      loras: current.loras.filter((_, itemIndex) => itemIndex !== index),
                    }
                    saveSettings({ loras: updated.loras })
                    return updated
                  })
                }}
                disabled={disabled}
              >
                ×
              </button>
            </div>
          ))}
        </div>

        {error && <p className="form-error">{error}</p>}
        <div className="generation-actions">
          <button className="primary-button generate-button" type="submit" disabled={disabled}>
            <span className="play-icon">▶</span> Generate
          </button>
          <div className="story-generation-action">
            <button
              className="secondary-button generate-story-button"
              type="button"
              title="Will write story arc and beats based on story.txt"
              onClick={generateStory}
              disabled={disabled}
            >
              Generate Story
            </button>
            <NumberField
              label="Beats"
              value={settings.beat_count}
              onChange={(event) => setField('beat_count', event.target.value)}
              placeholder="12"
              title="Number of story beats to write"
              min="1"
              step="1"
              disabled={disabled}
            />
          </div>
        </div>
      </form>
    </section>
  )
}
