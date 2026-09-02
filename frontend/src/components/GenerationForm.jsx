import { useMemo, useState } from 'react'

const INITIAL_SETTINGS = {
  segment_length: '',
  total_length: '',
  megapixels: '',
  resume: '1',
  steps: '6',
  context_frames: '7',
  refresh: '6',
  repair: '',
  model: 'ministral',
  first_frame: false,
  loras: [],
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

export default function GenerationForm({ disabled, onGenerate }) {
  const [settings, setSettings] = useState(INITIAL_SETTINGS)
  const [mode, setMode] = useState('new')
  const [error, setError] = useState('')

  const totalSegments = useMemo(() => {
    const segment = Number(settings.segment_length)
    const total = Number(settings.total_length)
    return segment > 0 && total > 0 ? Math.ceil(total / segment) : null
  }, [settings.segment_length, settings.total_length])

  const setField = (field, value) => {
    setSettings((current) => ({ ...current, [field]: value }))
  }

  const changeMode = (nextMode) => {
    setMode(nextMode)
    setSettings((current) => ({
      ...current,
      resume: nextMode === 'resume' ? current.resume : '1',
      repair: nextMode === 'repair' ? current.repair : '',
    }))
  }

  const updateLora = (index, field, value) => {
    setSettings((current) => ({
      ...current,
      loras: current.loras.map((lora, itemIndex) =>
        itemIndex === index ? { ...lora, [field]: value } : lora,
      ),
    }))
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

        <div className="lora-section">
          <div className="subheading-row">
            <div>
              <h3>Global LoRAs</h3>
              <p>Applied in this order to every beat.</p>
            </div>
            <button
              className="secondary-button compact"
              type="button"
              onClick={() =>
                setSettings((current) => ({
                  ...current,
                  loras: [...current.loras, { name: '', strength: '1' }],
                }))
              }
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
                onClick={() =>
                  setSettings((current) => ({
                    ...current,
                    loras: current.loras.filter((_, itemIndex) => itemIndex !== index),
                  }))
                }
                disabled={disabled}
              >
                ×
              </button>
            </div>
          ))}
        </div>

        {error && <p className="form-error">{error}</p>}
        <button className="primary-button generate-button" type="submit" disabled={disabled}>
          <span className="play-icon">▶</span> Generate
        </button>
      </form>
    </section>
  )
}
