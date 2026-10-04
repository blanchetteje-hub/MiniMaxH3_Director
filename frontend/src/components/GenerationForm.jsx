import { useEffect, useState } from 'react'
import { invokeBridge } from '../lib/pywebview.js'
import HelpTip from './HelpTip.jsx'

const INITIAL_SETTINGS = {
  generation_mode: 'new', vram_mode: '32', segment_length: '', total_segments: '',
  megapixels: '0.5', resume: '1', steps: '6', trim_frames: '2', refresh: '999',
  vision_continuity: '0', retention: false, repair: '', model: 'gpt', temp: '0.4', first_frame: false,
  loras: [], beat_count: '', beat_length: '', use_prompts: '',
  test_prompt_generation: false, director_only: false,
  capture_h3_segment: '', capture_h3_fixture: '', capture_h3_validation_segment: '',
  capture_h3_validation_fixture: '',
}
const MODES = [
  ['new', 'New', 'Start with story.txt. Rebuild beats and generate the finished video.'],
  ['existing', 'Existing', 'Use your existing beats.txt without rebuilding the story beats.'],
  ['render_only', 'Render-Only', 'Render generated_prompts.txt through ComfyUI. No LLM is needed.'],
]

function Field({ label, help, children }) {
  return <div className="field"><span className="field-label">{label} <HelpTip>{help}</HelpTip></span>{children}</div>
}

export default function GenerationForm({ disabled, onGenerate, onGenerateStory }) {
  const [settings, setSettings] = useState(INITIAL_SETTINGS)
  const [error, setError] = useState('')
  useEffect(() => {
    invokeBridge('get_settings').then(saved => setSettings(current => ({ ...current, ...Object.fromEntries(Object.keys(INITIAL_SETTINGS).filter(key => saved[key] != null).map(key => [key, saved[key]])),
      loras: Array.isArray(saved.loras) ? saved.loras : [],
    }))).catch(() => {})
  }, [])
  const setField = (key, value) => {
    setSettings(current => ({ ...current, [key]: value }))
    invokeBridge('save_settings', { [key]: value }).catch(() => {})
  }
  const mode = settings.generation_mode
  const limited = settings.vram_mode === '16'
  const rendering = mode === 'render_only'
  const input = (key, label, help, type = 'number', extra = {}) => <Field label={label} help={help}>
    <input aria-label={label} type={type} value={settings[key] ?? ''} onChange={event => setField(key, event.target.value)} disabled={disabled} {...(type === 'number' ? { min: '0', step: '1' } : {})} {...extra} />
  </Field>
  const check = (key, label, help) => <div className="checkbox-option"><label className="checkbox-field"><input type="checkbox" checked={Boolean(settings[key])} onChange={event => setField(key, event.target.checked)} disabled={disabled} /><span>{label}</span></label><HelpTip>{help}</HelpTip></div>
  const submit = (action) => {
    setError('')
    if (action !== 'render' && !rendering) {
      if (!(Number(settings.segment_length) > 0) || !Number.isInteger(Number(settings.total_segments)) || Number(settings.total_segments) < 1) {
        setError('Enter a positive clip duration and a whole number of segments.'); return
      }
    }
    if (action !== 'render' && !rendering && settings.loras.some(lora => !lora.name.trim() || !Number.isFinite(Number(lora.strength)) || lora.strength === '')) {
      setError('Each LoRA needs a filename and a numeric strength.'); return
    }
    const selectedDiagnostics = ['test_prompt_generation', 'director_only'].filter(key => settings[key])
    if (!limited && !rendering && selectedDiagnostics.length > 1) { setError('Choose only one advanced prompt generation alternative.'); return }
    onGenerate(action === 'render' || rendering
      ? { generation_mode: 'render_only', vram_mode: settings.vram_mode, action: 'render', use_prompts: limited ? '' : settings.use_prompts, test_prompt_generation: false, director_only: false, capture_h3_segment: '', capture_h3_fixture: '', capture_h3_validation_segment: '', capture_h3_validation_fixture: '', repair: null, resume: '1', first_frame: false, loras: [] }
      : { ...settings, use_prompts: '', director_only: mode === 'existing' && settings.director_only, ...(limited ? { test_prompt_generation: false, director_only: false, capture_h3_segment: '', capture_h3_fixture: '', capture_h3_validation_segment: '', capture_h3_validation_fixture: '', vision_continuity: '0', use_prompts: '' } : {}), action, resume: mode === 'new' || limited ? '1' : settings.resume, repair: mode === 'new' || limited ? null : settings.repair || null })
  }
  const updateLora = (index, key, value) => setField('loras', settings.loras.map((item, n) => n === index ? { ...item, [key]: value } : item))
  const generateBeats = async () => {
    setError('')
    if (!Number.isInteger(Number(settings.beat_count)) || Number(settings.beat_count) < 1 || !(Number(settings.beat_length || settings.segment_length) > 0)) {
      setError('Enter a positive whole beat count and beat duration.'); return
    }
    const result = await onGenerateStory({ ...settings, beat_length: settings.beat_length || settings.segment_length })
    if (result && !result.ok) setError(result.error)
  }
  return <section className="panel settings-panel">
    <div className="panel-heading"><div><p className="eyebrow">Create your video</p><h2>Generation settings</h2></div>
      {Number(settings.segment_length) > 0 && Number(settings.total_segments) > 0 && <span className="calculated">{settings.total_segments} clips · {Number(settings.segment_length) * Number(settings.total_segments)} seconds</span>}
    </div>
    <form onSubmit={event => { event.preventDefault(); submit(rendering ? 'render' : limited ? 'prompts' : 'generate') }}>
      <div className="mode-group generation-tabs" role="tablist" aria-label="Generation source">
        {MODES.map(([value, label, help]) => <div className="generation-tab" key={value}><button type="button" id={`tab-${value}`} role="tab" aria-selected={mode === value} aria-controls="generation-options" className={`mode-button ${mode === value ? 'selected' : ''}`} onClick={() => { setField('generation_mode', value); if (value === 'new') setField('director_only', false) }} tabIndex={mode === value ? 0 : -1} onKeyDown={event => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const index = MODES.findIndex(item => item[0] === mode); const next = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3; setField('generation_mode', MODES[next][0]); if (next === 0) setField('director_only', false); document.getElementById(`tab-${MODES[next][0]}`)?.focus() } }} disabled={disabled}>{label}</button><HelpTip>{help}</HelpTip></div>)}
      </div>
      <div id="generation-options" role="tabpanel" aria-labelledby={`tab-${mode}`}>
        <p className="mode-description">{MODES.find(item => item[0] === mode)?.[2]}</p>
        <Field label="VRAM mode" help="16GB separates prompt creation and video rendering so the LLM and ComfyUI can run one at a time. 32GB+ can run the complete pipeline.">
          <select aria-label="VRAM mode" value={settings.vram_mode} onChange={event => setField('vram_mode', event.target.value)} disabled={disabled}><option value="32">32GB+ — complete pipeline</option><option value="16">16GB — separate LLM and ComfyUI</option></select>
        </Field>
        {limited && <p className="inline-callout">First generate prompts with your LLM running. Then stop the LLM, start ComfyUI, and generate video using the saved prompts.</p>}
        {!rendering && <div className="field-grid primary-fields">
          {input('segment_length', 'Clip duration (seconds)', 'Length of each clip. Five 8-second clips produce a 40-second video.', 'number', { min: '0.01', step: 'any', placeholder: '8' })}
          {input('total_segments', 'Number of segments', 'Total number of clips to generate, not the total duration.', 'number', { min: '1', placeholder: '5' })}
          {input('megapixels', 'Resolution (megapixels)', 'Target resolution for initial and refresh clips. Higher values require more VRAM.', 'number', { min: '0.01', step: 'any' })}
        </div>}
        {rendering && <p className="muted-note">Clip count, duration, and workflow metadata come from the saved prompt package.</p>}
        {!rendering && <details className="advanced"><summary>Rendering & continuity</summary><div className="field-grid">
          {input('steps', 'Sampling steps', 'ComfyUI sampling steps. More steps may improve quality but take longer.', 'number', { min: '1' })}
          {input('trim_frames', 'Trim frames', 'Frames removed from each clip after the first when stitching the final video.')}
          {!rendering && input('refresh', 'Refresh interval', 'Compatibility fallback: regenerate from the preceding clip’s last frame every N segments.', 'number', { min: '1' })}
          {!rendering && !limited && input('vision_continuity', 'Vision continuity interval', 'Check rendered frames every N segments. 0 disables checks; requires both the LLM and ComfyUI.')}
        </div></details>}
        {!rendering && <details className="advanced"><summary>Prompt & story options</summary><div className="field-grid">
          {mode === 'new' && input('temp', 'Story temperature', 'Controls creativity in the initial story-writing LLM call only (--temp). Default: 0.4. Zero is allowed; later LLM calls keep their own settings.', 'number', { min: '0', step: 'any' })}
          <Field label="Response formatter" help="Choose how the LLM response is parsed. Match this to your configured model."><select aria-label="Response formatter" value={settings.model} onChange={event => setField('model', event.target.value)} disabled={disabled}><option value="gpt">GPT</option><option value="mistral">Mistral</option><option value="qwen">Qwen</option></select></Field>
        </div>{check('retention', 'Include retention analysis', 'Append retention analysis to every clip after the first.')}{check('first_frame', 'First-frame instructions', 'Add first-frame guidance to the prompt for segment 1.')}
        {!limited && mode === 'new' && <div className="story-tools"><p>Prepare beats separately without rendering a video.</p><div className="field-grid">{input('beat_count', 'Story beat count', 'Number of beats to write from story.txt using Generate Beats.', 'number', { min: '1' })}{input('beat_length', 'Beat duration (seconds)', 'Duration per story beat. If blank, use clip duration.', 'number', { min: '0.01', step: 'any' })}</div><button type="button" className="secondary-button" disabled={disabled} onClick={generateBeats}>Generate Beats</button></div>}
        </details>}
        <details className="advanced"><summary>{rendering ? 'Reference images' : 'Reference images & LoRAs'}</summary><p className="muted-note">Set all six reference image overrides in Defined Images above. Their order determines Picture 1 through Picture 6. Edit project files below for character definitions.</p><div className="field-grid"></div>
          {!rendering && <><div className="subheading-row"><h3>Global LoRAs <HelpTip>Apply these LoRAs in order to every beat.</HelpTip></h3><button type="button" className="secondary-button compact" disabled={disabled} onClick={() => setField('loras', [...settings.loras, { name: '', strength: '1' }])}>+ Add LoRA</button></div>
          {settings.loras.map((lora, i) => <div className="lora-row" key={i}><Field label={`LoRA ${i + 1} filename`} help="Filename of a LoRA in your LoRA directory."><input aria-label={`LoRA ${i + 1} filename`} value={lora.name} disabled={disabled} placeholder="filename.safetensors" onChange={event => updateLora(i, 'name', event.target.value)} /></Field><Field label="Strength" help="Weight applied to this LoRA. 1 is full strength; 0 disables its effect."><input aria-label={`LoRA ${i + 1} strength`} type="number" step="any" value={lora.strength} disabled={disabled} onChange={event => updateLora(i, 'strength', event.target.value)} /></Field><button type="button" className="icon-button" disabled={disabled} aria-label={`Remove LoRA ${i + 1}`} onClick={() => setField('loras', settings.loras.filter((_, n) => n !== i))}>×</button></div>)}</>}
        </details>
        {mode === 'existing' && !limited && <details className="advanced"><summary>Resume & repair</summary><div className="field-grid">{input('resume', 'Resume at segment', 'Continue from this one-based segment. Earlier segments must exist in generation_state.json.', 'number', { min: '1' })}{input('repair', 'Repair segment', 'Rerender only an existing middle segment with clips on both sides. Leave blank for normal generation.', 'number', { min: '2' })}</div></details>}
        {(!limited || !rendering) && <details className="advanced"><summary>Advanced & development</summary>
          {!limited && rendering && input('use_prompts', 'Saved prompt package', 'Custom prompt package path for Render-Only or Generate Video. Leave blank to use generated_prompts.txt.', 'text', { placeholder: 'generated_prompts.txt' })}
          {!limited && !rendering && <><p className="muted-note">These alternatives replace normal video generation and do not render. Choose at most one.</p>{check('test_prompt_generation', 'Preview prompts in the log', 'Generate and print all prompts without submitting to ComfyUI.')}{mode === 'existing' && check('director_only', 'Director only', 'Use existing story_arc.json and beats.txt; run only the Director prompt pipeline.')}</>}
          {!limited && !rendering && <div className="field-grid">{input('capture_h3_segment', 'Capture rendered segment', 'Development fixture: one-based segment number to capture. Requires a fixture path.', 'number', { min: '1' })}{input('capture_h3_fixture', 'Rendered fixture path', 'Destination for the captured development H3 fixture.', 'text')}{input('capture_h3_validation_segment', 'Capture validation segment', 'One-based segment whose accepted scene and final H3 prompt are saved for replay.', 'number', { min: '1' })}{input('capture_h3_validation_fixture', 'Validation fixture path', 'Destination for the captured final-prompt validation fixture.', 'text')}</div>}
        </details>}
      </div>
      {error && <p role="alert" className="form-error">{error}</p>}
      <div className="generation-actions">
        {limited ? <><button type="submit" className="primary-button generate-button" disabled={disabled || rendering}>Generate Prompts (LLM)</button><button type="button" className="secondary-button generate-button" disabled={disabled} onClick={() => submit('render')}>Generate Video (ComfyUI)</button></> : <button type="submit" className="primary-button generate-button" disabled={disabled}>▶ Generate</button>}
      </div>
    </form>
  </section>
}
