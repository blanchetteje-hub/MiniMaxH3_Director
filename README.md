# MiniMax H3 Continuous Video Automation

Generate a continuous, story-driven video as a sequence of MiniMax H3 clips.
The program uses:

- **LM Studio** to turn a story and ordered beat list into one directed shot at
  a time.
- **ComfyUI** to render the first clip and extend it with later clips.
- **FFmpeg** to remove overlap frames and concatenate the clips into a final
  MP4.

The automation checkpoints every successful segment, tracks completed story
beats, and keeps LM Studio context bounded to a five-bullet continuity summary
plus the two newest exact prompts. An interrupted run can resume without
regenerating completed clips.

> **Platform note:** the complete workflow runs on Windows or Linux. Python
> invokes FFmpeg directly for final stitching. `stitch.bat` is retained only as
> an optional Windows convenience.

## What the pipeline does

1. Reads `story.txt`, `beats.txt`, and optional `subjects.txt`.
2. Requests a structured shot description from an LM Studio model.
3. Normalizes and validates that description locally with deterministic Python
   rules, then inserts it into the correct ComfyUI API workflow.
4. Generates the initial clip or extends the previous clip.
5. Saves beat progress and an atomic resume checkpoint after each successful
   clip.
6. Trims two overlap frames from every clip after the first.
7. Concatenates the clips into `final.mp4`.

## Before you begin

You need:

- Windows 10/11 or a current Linux distribution.
- A recent NVIDIA GPU and enough system RAM, VRAM, and disk space for the
  MiniMax H3 model. Start at `0.2` megapixels if you are unsure what your GPU
  can handle.
- [Git](https://git-scm.com/downloads).
- [Python 3.10 or newer](https://www.python.org/downloads/).
- [ComfyUI 0.30.0 or newer](https://docs.comfy.org/installation/).
- [LM Studio](https://lmstudio.ai/download).
- [FFmpeg](https://ffmpeg.org/download.html), including both `ffmpeg` and
  `ffprobe` on `PATH`.

The model downloads are large. Confirm that the drive containing
`ComfyUI/models` has substantial free space before starting.

## Quick-start checklist

Complete these once, in order:

1. Install Python and this project's Python dependency.
2. Install or update ComfyUI.
3. Install the five required custom-node packages.
4. Download the seven model/LoRA files selected by the supplied workflows.
5. Place six reference images in `ComfyUI/input` and update both workflow JSON
   files to use them.
6. Load an LLM in LM Studio and start its local API server.
7. Set connection and output-path environment variables if their defaults do
   not match your system.
8. Create `story.txt`, `beats.txt`, and optionally `subjects.txt`.
9. Run the preflight commands, then start a short test generation.

The following sections explain each step.

## 1. Set up Python

Run these commands from the project directory.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, either allow locally created scripts for your
user account or call the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verify the installation:

```powershell
python --version
python -c "import requests; print(requests.__version__)"
```

Only the `requests` package is required by `minimax.py`.

### Linux

On Debian or Ubuntu, install Python and FFmpeg, then create an isolated Python
environment:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ffmpeg
cd /path/to/automate_git
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Use your distribution's equivalent package names when necessary.

## 2. Install and update ComfyUI

Install ComfyUI using the
[official installation instructions](https://docs.comfy.org/installation/) or
use an existing installation.

MiniMax H3 support is native in ComfyUI 0.30.0 and newer. Update older
installations before loading these workflows. The supplied workflows use native
MiniMax H3, AV decoding, video creation, math-expression, and resolution nodes.

Start ComfyUI and leave it running while the automation is active. Its default
address is:

```text
http://127.0.0.1:8188
```

Check the server from PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8188/system_stats
```

A JSON response means the API is reachable. There is no separate API-mode
switch required for a normal local ComfyUI server.

## 3. Install the required ComfyUI custom nodes

The easiest method is ComfyUI Manager: open **Manager**, choose **Install
Custom Nodes**, search for each package below, install it, and restart ComfyUI.

| Package | Nodes used by these workflows |
|---|---|
| [ComfyUI-MiniMax-H3-Turbo](https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo) | `MiniMaxH3TurboLoRA` |
| [ComfyUI-MiniMax-H3-Extend](https://github.com/kat3ri/ComfyUI-MiniMax-H3-Extend) | `MiniMaxH3VideoExtendPatched`, `MiniMaxH3EncodeAVPatched` |
| [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) | `PathchSageAttentionKJ`, `ImageBatchMulti` |
| [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | `VHS_LoadVideoPath` |
| [ComfyUI-DynamicPrompts](https://github.com/adieyal/comfyui-dynamicprompts) | `DPRandomGenerator` |

Even though Python replaces the prompt text, Dynamic Prompts must still be
installed because the workflow contains a `DPRandomGenerator` node.

### Manual custom-node installation

If a package is unavailable in Manager, open PowerShell in
`ComfyUI/custom_nodes` and clone it:

```powershell
git clone https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo.git
git clone https://github.com/kat3ri/ComfyUI-MiniMax-H3-Extend.git
git clone https://github.com/kijai/ComfyUI-KJNodes.git
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
git clone https://github.com/adieyal/comfyui-dynamicprompts.git
```

Install each package's Python requirements with the same Python environment
used by ComfyUI, then restart ComfyUI. For a portable build, that is normally
`python_embeded/python.exe`, not your system Python.

### Optional SageAttention acceleration

The workflows contain KJNodes' `Patch Sage Attention KJ` node. SageAttention
can improve speed but is an optional, hardware-specific dependency. Install a
wheel matching the exact PyTorch and CUDA versions in your ComfyUI environment.
If you do not install it, disable or bypass Sage Attention in the workflow and
export the API workflow again.

## 4. Download the required models

The base model, text encoder, and VAEs are available from
[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3). The Turbo
node and current Turbo weights are documented in
[Larryvrh/ComfyUI-MiniMax-H3-Turbo](https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo).

The supplied API workflows currently select these exact relative paths:

```text
ComfyUI/
└── models/
    ├── diffusion_models/
    │   ├── minimax_h3_fl2va_pruned_int8_convrot.safetensors
    │   └── minimax_h3_ref2va_pruned_int8_convrot.safetensors
    ├── text_encoders/
    │   └── qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
    ├── vae/
    │   ├── minimax_h3_audio_vae_fp32.safetensors
    │   └── minimax_h3_video_vae_fp16.safetensors
    └── loras/
        └── MiniMaxH3/
            ├── minimax_h3_turbo_v4_step600_pruned_comfyui.safetensors
            └── minimax_h3_ref2v_turbo_4step_v0.1_comfyui.safetensors
```

Both LoRAs are required:

- The initial workflow selects
  `minimax_h3_turbo_v4_step600_pruned_comfyui.safetensors`.
- The append workflow selects
  `minimax_h3_ref2v_turbo_4step_v0.1_comfyui.safetensors`.
Nested model paths use `/` in the checked-in JSON. Python converts those paths
to the separator expected by the current operating system before submitting a
workflow, so the same JSON works on Windows and Linux.

Both diffusion models are also required because each workflow uses the model
family matched to its task:

- The initial workflow uses `fl2va` with the general v4 Turbo LoRA.
- The append workflow uses `ref2va` with the reference-to-video Turbo LoRA to
  prioritize reference fidelity during continuation.

> **Important filename note:** these are the custom/local filenames currently
> selected by the checked-in workflows. Current public repositories use names
> such as `minimax_h3_turbo_v4_step600_ema.safetensors` and
> `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors`. A new user must
> either obtain the exact selected files or download compatible public weights,
> choose those files in the corresponding **MiniMax-H3 Turbo LoRA** node, and
> export updated API JSON. A differently named file is not selected
> automatically.

Do not interchange `fl2va` and `ref2va` as a setup shortcut. They are different
model families for different conditioning modes, and each supplied workflow now
selects its intended model explicitly.

After adding models, restart ComfyUI so its model lists refresh.

## 5. Configure the six reference images

Both workflows expect six ordered reference images. Their order must stay
consistent between the initial and append workflow:

| Prompt tag | Initial workflow input | Append workflow input |
|---|---|---|
| `<Picture 1>` | `ref_images.ref_image_0` | `Image Batch Multi.image_1` |
| `<Picture 2>` | `ref_images.ref_image_1` | `Image Batch Multi.image_2` |
| `<Picture 3>` | `ref_images.ref_image_2` | `Image Batch Multi.image_3` |
| `<Picture 4>` | `ref_images.ref_image_3` | `Image Batch Multi.image_4` |
| `<Picture 5>` | `ref_images.ref_image_4` | `Image Batch Multi.image_5` |
| `<Picture 6>` | `ref_images.ref_image_5` | `Image Batch Multi.image_6` |

The checked-in workflows currently use `0.png` as a placeholder in all six
`Load Image` nodes. At minimum, `0.png` must exist in `ComfyUI/input` or ComfyUI
will reject the workflow. For real identity continuity:

1. Copy up to six reference images into `ComfyUI/input`.
2. In both workflows, assign them to the clearly titled `Reference Image 1`
   through `Reference Image 6` nodes in the same order.
3. Export each workflow in **API format**, keeping these filenames:
   `Minimax_auto_API.json` and `Minimax_auto_append_API.json`.
4. Keep the automation-controlled node titles unchanged: `Float (duration)`,
   `Prompt`, `RandomNoise`, `Save Video`, `Resolution Selector`, `Reference
   Image 1` through `Reference Image 6`, `Image Batch Multi`, and `Load Video
   (Path) 🎥🅥🅗🅢`.

Numeric ComfyUI node IDs may change when you export. That is safe: the Python
program finds automation-controlled nodes by title, not by node number.

## 6. Set up LM Studio

1. Install and open [LM Studio](https://lmstudio.ai/).
2. Download and load an instruction-following model.
3. Give the model a context window of at least about 21,000 tokens. The script
   reserves up to 14,000 estimated input tokens and up to 4,000 output tokens.
4. In LM Studio's **Developer** area, start the local API server.
5. Confirm that the model supports the OpenAI-compatible chat-completions
   endpoint and structured JSON-schema output.

The default LM Studio server is commonly available at:

```text
http://127.0.0.1:1234
```

The checked-in `minimax.py` defaults to `http://192.168.0.203:1234`. Override
`MINIMAX_LM_STUDIO_URL` for a different server. Requests explicitly select
`ministral-3-14b-instruct-2512-absolute-heresy.i1-q5_k_m_gguf` by default;
override `MINIMAX_LM_STUDIO_MODEL` when LM Studio exposes a different model ID.
If LM Studio and this script run on the same computer, use:

```powershell
$env:MINIMAX_LM_STUDIO_URL = "http://127.0.0.1:1234"
```

Test the server from PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:1234/v1/models
```

For remote LM Studio hosts, enable network serving in LM Studio, use the host
computer's LAN IP, and allow the port through its firewall.

## 7. Configure URLs and paths

Configuration uses environment variables, so you do not need to edit Python.
Linux defaults to `~/ComfyUI` and `~/ComfyUI/output`. The original Windows
defaults are retained. Override any value that differs on your computer.

Linux (`bash` or `zsh`):

```bash
export MINIMAX_COMFYUI_ROOT="$HOME/ComfyUI"
export MINIMAX_COMFYUI_OUTPUT="$HOME/ComfyUI/output"
export MINIMAX_VIDEO_OUTPUT="$HOME/ComfyUI/output/video"
export MINIMAX_COMFY_URL="http://127.0.0.1:8188"
export MINIMAX_LM_STUDIO_URL="http://127.0.0.1:1234"
export MINIMAX_LM_STUDIO_MODEL="ministral-3-14b-instruct-2512-absolute-heresy.i1-q5_k_m_gguf"
```

Windows PowerShell:

```powershell
$env:MINIMAX_COMFYUI_ROOT = "C:\ComfyUI_windows_portable\ComfyUI"
$env:MINIMAX_COMFYUI_OUTPUT = "H:\images\output"
$env:MINIMAX_VIDEO_OUTPUT = "H:\images\output\video"
$env:MINIMAX_COMFY_URL = "http://127.0.0.1:8188"
$env:MINIMAX_LM_STUDIO_URL = "http://192.168.0.203:1234"
$env:MINIMAX_LM_STUDIO_MODEL = "ministral-3-14b-instruct-2512-absolute-heresy.i1-q5_k_m_gguf"
```

`MINIMAX_COMFYUI_OUTPUT` must be the output directory used by the ComfyUI
instance at `MINIMAX_COMFY_URL`. ComfyUI and this script must see generated
files at the same path. For a container or remote server, mount or share that
directory accordingly.

## 8. Install and verify FFmpeg

Install [FFmpeg](https://ffmpeg.org/download.html) and make sure its executables
are on `PATH`. Open a new terminal and verify both commands:

```powershell
ffmpeg -version
ffprobe -version
```

`ffprobe` validates each generated clip's resolution. Python calls `ffmpeg` to
trim overlap frames and concatenate the completed clips. `stitch.bat` is not
required for normal runs.

## 9. Prepare the project inputs

Project inputs and workflows resolve relative to `minimax.py`, so the program
can be launched from another working directory.

### `story.txt` — required

Write the source story or creative brief. It can include setting, characters,
tone, dialogue, clothing, and desired camera behavior.

### `beats.txt` — optional beat tracking

Write one required story event per non-empty line, in chronological order:

```text
Introduce Mark and his family at the crowded theme park.
Flying saucers appear above the park.
The saucers abduct Mark's family while they flee.
```

Blank lines and lines beginning with `#` are ignored. The order is
authoritative, and the director cannot mark a later beat complete before an
earlier one. Leave the file blank (or use only comments) to disable the beat
scheduler. Story generation then follows `story.txt` directly without beat
deadlines, completion updates, or `beat_progress.txt` writes.

### `subjects.txt` — optional

Describe persistent subjects and map them to the reference-image tags:

```text
Mark is a 40-year-old man referenced in <Picture 1>.
Elena is Mark's wife, referenced in <Picture 2>.
Their red backpack is referenced in <Picture 3>.
```

Use `<Picture N>` exactly, matching the reference order in both workflows.
The filename is `subjects.txt`, not `subject_definitions.txt`.

### Continuity safeguards

Beginning after prompt 2, the script asks LM Studio for exactly five bullet
points summarizing the newest two generated prompts. This uses a separate,
stateless chat-completions message list and is independent of the director's
Python-first content-correction thread. One background worker runs this request
while ComfyUI renders the current clip.

Before the next director request, the script waits for the summary if needed.
The director receives that summary and only the newest two exact prompts;
earlier prompts are never accumulated in its request. The rendered segment is
checkpointed before waiting for the summary, then the checkpoint is updated
with the five bullets. If that update is interrupted, resume rebuilds the
pending summary from the two saved prompt results without rerendering video.

### Beat pacing

Every beat receives a hard completion deadline based on the requested segment
and beat counts. For example, a 100-segment run with 50 beats schedules B001
by segment 2, B002 by segment 4, and so on. On a beat's deadline segment, the
director must visibly complete it and include its ID in `completed_beat_ids`.
Every response is first normalized and validated by deterministic Python rules.
Formatting problems that can be repaired without changing story content do not
cause another LM Studio request. Only unresolved content problems, such as a
missing required action or dialogue, may trigger a corrected full response,
with at most two content-correction requests. Each corrected response goes
through the same local formatter and validator. If it is still invalid, the run
stops before sending anything to ComfyUI. Network/transport retries are counted
separately from these content corrections.

## 10. Preflight before the first generation

Confirm all of the following:

- ComfyUI is running and `/system_stats` responds.
- LM Studio is running, a model is loaded, and `/v1/models` responds.
- `python -c "import requests"` succeeds.
- `ffmpeg -version` and `ffprobe -version` succeed.
- ComfyUI starts without reporting missing workflow nodes.
- All seven base/LoRA/VAE/text-encoder files selected by the workflows appear in
  ComfyUI.
- Every reference image exists under `ComfyUI/input`.
- `MINIMAX_COMFYUI_OUTPUT` points to the real ComfyUI output directory.
- `story.txt` is non-empty. `beats.txt` either contains ordered beats or is blank
  to disable beat tracking.

For the first test, use a short run and low resolution:

```powershell
python minimax.py 5 10 0.2
```

This requests two five-second segments at approximately 0.2 megapixels for the
initial clip.

## Running the program

The three main settings are positional arguments:

```text
python minimax.py SEGMENT_LENGTH TOTAL_LENGTH MEGAPIXELS [--resume SEGMENT]
```

Separate values with spaces as shown above. For convenience, commas are also
accepted, including both `python minimax.py 5, 10, .2` and
`python minimax.py 5,10,.2`.

| Argument | Meaning |
|---|---|
| `SEGMENT_LENGTH` | Target seconds generated per segment; must be greater than zero. |
| `TOTAL_LENGTH` | Target total movie length in seconds; must be greater than zero. |
| `MEGAPIXELS` | Initial workflow resolution target; must be greater than zero. |
| `--resume SEGMENT` | Continue at this one-based segment number; defaults to `1`. |

### Example: new 60-second run

```powershell
python minimax.py 5 60 0.5
```

This creates 12 segments. Starting a new run with the default resume value of
`1` starts a new checkpoint and resets beat progress.

### Example: resume at segment 12

Use the exact same first three values as the interrupted run:

```powershell
python minimax.py 5 60 0.5 --resume 12
```

Resume means segments 1–11 must already have successful checkpoint records.
Before contacting LM Studio or ComfyUI, the script checks the saved run
settings, source-file signature, ordered segment records, formatted director
results, and every prior video path. It restores beat completion, recent
director context, and the video chain used for final stitching. If `story.txt`,
`beats.txt`, or `subjects.txt` changed after the checkpoint, restore the
original inputs or start a new run.

## Generated files

| File or folder | Purpose |
|---|---|
| `generation_state.json` | Atomic checkpoint containing settings, director results, beat state, continuity summary, and video paths. |
| `beat_progress.txt` | Readable DONE/NEXT/TODO beat checklist. |
| ComfyUI `output/video/segment_*.mp4` | Individual generated clips. |
| ComfyUI `output/video/trimmed_segment_*.mp4` | Stitch-ready clips after overlap removal. |
| ComfyUI `output/video/list.txt` | Automatically generated FFmpeg concat list. |
| ComfyUI `output/video/final.mp4` | Final concatenated movie. |

## Workflow validation

Before contacting LM Studio or generating video, the program validates the
workflow JSON and the named nodes it controls:

- `Float (duration)`
- `Prompt`
- `RandomNoise`
- `Save Video`
- `Resolution Selector` in the initial workflow
- `Reference Image 1` through `Reference Image 6` in both workflows
- `Image Batch Multi` with those six sources connected in the correct order in
  the append workflow
- `Load Video (Path) 🎥🅥🅗🅢` in the append workflow
- The append duration/math, prompt, previous-video encoding, reference-image,
  conditioning, latent, decoding, and save-video connections

Node types and required input fields are also checked. If you customize a
workflow, preserve these titles or update the matching constants in
`minimax.py`.

## Continuity and beat tracking

- Each segment is exactly one directed shot.
- Exactly the newest two generated prompts are kept verbatim for immediate
  continuity.
- Starting after prompt 2, a separate LM Studio request refreshes an exact
  five-bullet summary of that two-prompt window after every new segment.
- The next director request receives the summary and those two exact prompts,
  instead of accumulated prompt history.
- Beat completion is accepted only as a contiguous prefix of `beats.txt`, so a
  model cannot silently skip a required event.
- A single background LM Studio worker refreshes the five bullets while
  ComfyUI renders the current segment.

## Troubleshooting

### “Missing ComfyUI node named ...”

1. Update ComfyUI to 0.30.0 or newer.
2. Install every custom-node package listed above.
3. Restart ComfyUI and inspect its console for import errors.
4. If you renamed a controlled node, restore its expected title and export the
   workflow in API format again.

### ComfyUI rejects the workflow

- Confirm all selected model and LoRA filenames exist exactly as written.
- Confirm each `Load Image` filename exists in `ComfyUI/input`.
- Open ComfyUI Manager and use its missing-node check.
- Restart ComfyUI after installing nodes or models.

### LM Studio connection or JSON errors

- Confirm the model is loaded, not merely downloaded.
- Confirm the Developer API server is running.
- Test `/v1/models` at the same host configured in `LM_STUDIO_URL`.
- Use a model that supports structured JSON-schema output.
- Increase the loaded model's context window if the script reports that the
  fixed context exceeds its token budget.

### “ComfyUI reported a video output, but the file does not exist”

`MINIMAX_COMFYUI_OUTPUT` does not match the output directory of the ComfyUI
server at `MINIMAX_COMFY_URL`. Correct the environment variable and resume at
the failed segment.

### Resume cannot find prior videos

- Use the same segment length, total length, and megapixel value as the
  original run.
- Do not move or rename completed segment files.
- Do not change `beats.txt` during a run.
- Check `generation_state.json` for the first missing or moved segment video.

### Out of VRAM

- Lower the megapixel value.
- Shorten the segment length.
- Enable `low_vram` on the MiniMax-H3 Turbo LoRA node.
- Close other GPU-heavy applications.
- The script asks ComfyUI to free VRAM every five segments and after the final
  segment, but that cannot compensate for a single workflow that exceeds GPU
  capacity.

### FFmpeg or stitching errors

- Verify both `ffmpeg` and `ffprobe` are on `PATH`.
- Confirm the folder is writable.
- Delete no `segment_*.mp4` files until finalization finishes.

Python performs stitching directly. On Windows, `stitch.bat` can optionally be
copied beside the generated `list.txt` and run manually to repeat only the
final concatenation step.

To show a full Python traceback for an unexpected failure:

```powershell
$env:MINIMAX_DEBUG = "1"
python minimax.py 5 10 0.2
```

On Linux:

```bash
MINIMAX_DEBUG=1 python minimax.py 5 10 0.2
```

## Repository files

| File | Purpose |
|---|---|
| `minimax.py` | Main automation program. |
| `Minimax_auto_API.json` | Initial reference-to-video API workflow. |
| `Minimax_auto_append_API.json` | Video-continuation API workflow. |
| `story.txt` | Source story or creative brief. |
| `beats.txt` | Optional ordered story events; blank disables beat tracking. |
| `subjects.txt` | Optional subject/reference definitions. |
| `stitch.bat` | Optional Windows-only FFmpeg concat helper. |
| `requirements.txt` | Python package requirements. |
