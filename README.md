# MiniMax H3 Continuous Video Automation

Generate a continuous, story-driven video as a sequence of MiniMax H3 clips.
The program uses:

- **LM Studio** to turn a story and ordered beat list into one directed shot at
  a time.
- **ComfyUI** to render the first clip and extend it with later clips.
- **FFmpeg** to remove overlap frames and concatenate the clips into a final
  MP4.

The automation checkpoints every successful segment, tracks completed story
beats, and keeps LM Studio context bounded to structured continuity state plus
the two newest exact prompts. An interrupted run can resume without
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
3. Install the six required custom-node packages.
4. Download the seven model/LoRA files selected by the supplied workflows.
5. Place six reference images in `ComfyUI/input` and update both workflow JSON
   files to use them.
6. Load an LLM in LM Studio and start its local API server.
7. Set connection and output-path environment variables if their defaults do
   not match your system.
8. Create `story.txt`, `beats.txt`, and optionally `subjects.txt`.
9. Add the custom node supplied in this repo
10. Run the preflight commands, then start a short test generation.

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
| [MiniMax H3 Hybrid Cond](https://github.com/kitsune123150/minimax-h3-hybrid-cond) | `MiniMaxH3HybridRefAndKeyframe` used by the refresh workflow |

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
git clone https://github.com/kitsune123150/minimax-h3-hybrid-cond.git
```

Install each package's Python requirements with the same Python environment
used by ComfyUI, then restart ComfyUI. For a portable build, that is normally
`python_embeded/python.exe`, not your system Python.

### MiniMax H3 hybrid conditioning patch

The `minimax-h3-hybrid-cond` custom-node package contains
`model_base_patch.py`. This file is not part of `minimax.py`, the Save Latent
node, or the core ComfyUI source. The package imports it automatically from its
`__init__.py` when ComfyUI starts. It patches `MiniMaxH3.extra_conds` so the
refresh workflow can combine its extracted first-frame keyframe with the normal
reference images in one conditioning payload.

Some versions of this patch assume every keyframe dictionary contains a
`latent` value. A conditioning pass may retain keyframe layout metadata without
that value, producing this error before sampling and Save Latent can run:

```text
model_base_patch.py, line 30, in extra_conds_with_hybrid
KeyError: 'latent'
```

The corrected patch filters both keyframes and references with
`item.get("latent") is not None` before adding their latents. This matches the
defensive behavior in ComfyUI's native MiniMax H3 implementation while keeping
valid keyframe and reference latents in order. After installing the node, overwrite the model_base_patch.py in customnodes/minimax-h3-hybrid-cond folder with the file provided.  This is assuming they haven't patched it themselves by this point.

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

The checked-in workflows currently use `0.png` as a placeholder in the
reference `Load Image` nodes. Before any workflow is queued, the program checks
each configured image against the ComfyUI input folder and disconnects missing
slots. A missing image is therefore omitted from MiniMax H3 instead of causing
the workflow to fail. For real identity continuity:

1. Copy up to six reference images into `ComfyUI/input`.
2. In the initial and append workflows, assign them to the clearly titled
   `Reference Image 1` through `Reference Image 6` nodes in the same order. The
   refresh workflow receives the initial workflow's filenames automatically.
3. Export each workflow in **API format**, keeping these filenames:
   `Minimax_auto_API.json` and `Minimax_auto_append_API.json`.
4. Keep the automation-controlled node titles unchanged: `Float (duration)`,
   `Prompt`, `RandomNoise`, `Save Video`, `Resolution Selector`, `Reference
   Image 1` through `Reference Image 6`, `Image Batch Multi`, and `Load Video
   (Path) 🎥🅥🅗🅢`.

Numeric ComfyUI node IDs may change when you export. That is safe: the Python
program finds automation-controlled nodes by title, not by node number.

Each line in `beats.txt` may end with any number of beat-specific LoRA options:

```text
The portal opens --lora my_style.safetensors:0.8 --lora portal_glow.safetensors:0.45
```

The options are removed before beat text is sent to the LLM and apply while
that beat is active. Every option requires the exact
`[lora_name]:[strength]` form. There is no fallback LoRA and
`default.safetensors` is not required.

Repeat `--lora [lora_name]:[strength]` on the command line to apply any number
of global LoRAs to every beat. Beat-specific LoRAs are appended after the
global LoRAs in the order written; duplicate names are preserved. For each
segment, the program removes the workflow's blank placeholder when the merged
list is empty, reuses it for the first LoRA, and adds/chains as many additional
`LoraLoaderModelOnly` nodes as needed in both API workflows.

To automatically generate beats while applying one LoRA to every generated beat,
put only a file-level directive in `beats.txt` (comments and blank lines are also
allowed):

```text
--lora minimax_h3_lighting.safetensors:1.0
```

The directive is metadata, not a story beat. The program treats the file as empty,
generates the required number of beats, and appends the directive to every saved
beat. This legacy file-level metadata form also requires an explicit strength.

## 6. Set up LM Studio

Every LM Studio chat-completions request includes a randomly generated positive
31-bit `seed`. Transport retries receive a new seed, while the structured-output
fallback for the same attempt keeps that attempt's seed. The seed is also stored
in `prompt_history.txt` metadata so a request can be reproduced.

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
`MINIMAX_LM_STUDIO_URL` for a different server. The script does not send a
model name to LM Studio; it uses whichever chat model the user has loaded.
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
```

Windows PowerShell:

```powershell
$env:MINIMAX_COMFYUI_ROOT = "C:\ComfyUI_windows_portable\ComfyUI"
$env:MINIMAX_COMFYUI_OUTPUT = "H:\images\output"
$env:MINIMAX_VIDEO_OUTPUT = "H:\images\output\video"
$env:MINIMAX_COMFY_URL = "http://127.0.0.1:8188"
$env:MINIMAX_LM_STUDIO_URL = "http://192.168.0.203:1234"
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
concatenate the completed clips without trimming them. `stitch.bat` is not
required for normal runs.

## 9. Prepare the project inputs

Project inputs and workflows resolve relative to `minimax.py`, so the program
can be launched from another working directory.

### `story.txt` — required

Write the source story or creative brief. It can include setting, characters,
tone, dialogue, clothing, and desired camera behavior.

An optional `beat_instructions` directive supplies extra instructions verbatim
when LM Studio generates beats. Put it on its own line; it is removed from the
narrative before normal story generation:

```text
beat_instructions: [Make the midpoint a surprising silent reveal.]
```

When this directive is present, a separate compliance-edit request audits the
candidate beats before they are saved. Python also verifies common explicit
constraints such as exact phrase placement/count, prohibited words, required
phrases, and an exact final sentence; failed checks trigger another correction.

### `beats.txt` — optional beat tracking

Write one required story event per non-empty line, in chronological order:

```text
Introduce Mark and his family at the crowded theme park.
Flying saucers appear above the park.
The saucers abduct Mark's family while they flee.
```

Blank lines and lines beginning with `#` are ignored. The order is
authoritative, and the director cannot mark a later beat complete before an
earlier one. If the file is blank or contains only comments, the program first
asks LM Studio to create exactly one creative, non-repeating, forward-moving
beat per requested video segment. The final generated beat must conclude the
story. Every generated beat is restricted to exactly one complete sentence.
Python validates the sentence limit, exact count, and uniqueness; prints the
accepted beats as a numbered list; saves them to `beats.txt`; and then continues
through normal startup.

Beat generation uses a higher-creativity sampling profile than continuity and
formatting requests: `temperature=0.9`, `top_p=0.95`,
`presence_penalty=0.55`, `frequency_penalty=0.3`, and
`repeat_penalty=1.08`. The prompt also requires the model to consider multiple
distinct arcs and avoid generic filler, stock obstacles, and predictable plot
progression. Other LLM calls retain their conservative sampling defaults.

### `subjects.txt` — optional

Describe persistent subjects and map them to the reference-image tags:

```text
<Subject 1> is Mark, a 40-year-old man referenced in <Picture 1>.
<Subject 2> is Elena, Mark's wife, referenced in <Picture 2>.
```

Subject identity, Picture identity, and speaker identity are separate mappings.
An optional speaker mapping may be declared with `(S1)` on the subject line.
Picture references establish visual identity/body appearance only; they never
establish current clothing. Current wardrobe comes from the committed
continuity state or a successfully rendered wardrobe change.

If a rendered segment introduces a persistent subject that has no Picture
reference, the continuity updater assigns the next stable `<Subject N>` ID.
Only after that segment renders successfully, Python registers an internal
definition like this:

```text
<Subject 3> is spider-alien, created in generated video segment 2 and continued from <Video 1>.
```

The internal definition list and the same `origin_segment` are stored in
`generation_state.json`; `subjects.txt` is never modified. Later segments reuse
the ID and origin, combine the internal entry with the file-backed definitions
under `subject_definitions`, and use the immediately preceding `<Video 1>` as
that subject's visual reference. No Picture tag is invented for a video-created
subject. Internal definitions are excluded from the user-source fingerprint, so
registering them does not invalidate `--resume` for the active run.

When `beats.txt` is generated automatically, parsed subjects are sent to LM
Studio as the main characters. Canonical names and available descriptive
clauses (for example, `Mark is a 40-year-old man`) are included in both the
initial beat request and its compliance review. A subject with no description
is still included by name. Picture and speaker metadata are omitted.

Every non-comment line in a non-empty `subjects.txt` must parse as exactly one
unique subject definition. Startup stops with the line number and expected
format if any definition is malformed, so beat generation cannot silently omit
a main character. Immediately before each beat-generation or compliance-review
request, the program also verifies that the complete formatted subject list is
present in the LLM prompt.

Generated prose uses `Name <Picture N>` for visual identity and
`Name <Picture N> (S1) says:` for dialogue. Legacy `<Subject N>` forms are
accepted while older checkpoints are migrated.
The filename is `subjects.txt`, not `subject_definitions.txt`.

### Continuity safeguards

Beginning after prompt 2, the script asks LM Studio for exactly eight labeled
state fields summarizing the newest two generated prompts. This uses a separate,
stateless chat-completions message list and is independent of the director's
Python formatting and validation. The summary request runs after the current
clip has rendered and been checkpointed.

Before the next director request, the script waits for the summary if needed.
The director receives that summary and only the newest two exact prompts;
earlier prompts are never accumulated in its request. The rendered segment is
checkpointed before waiting for the summary, then the checkpoint is updated
with the eight state fields. If that update is interrupted, resume rebuilds the
pending summary from the two saved prompt results without rerendering video.

### Beat pacing

Every beat receives a hard completion deadline based on the requested segment
and beat counts. For example, a 100-segment run with 50 beats schedules B001
by segment 2, B002 by segment 4, and so on. On a beat's deadline segment, the
director must visibly complete it and include its ID in `completed_beat_ids`.
Every response is first normalized and validated by deterministic Python rules.
Formatting problems that can be repaired without changing story content do not
cause another LM Studio request. Unresolved content problems can trigger at most
two stateless correction requests containing exactly one system turn and one
user turn. If a
correction request fails or the corrected result remains invalid, the latest
best-effort locally formatted prompt continues to ComfyUI instead of stopping
the run. Network/transport retries remain separate.

## 10. Add custom node

A custom node was created for saving the state of the latents so no information would be lost when decoding/encoding video frames.
- Create a folder in your custom_nodes folder called "ComfyUI-h3_av_latent_io"
- Copy __init__.py to this folder
- Restart ComfyUI if needed

## 11. Preflight before the first generation

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
- `MINIMAX_COMFYUI_INPUT` points to the real ComfyUI input directory when it
  is not `ComfyUI/input`.
- `story.txt` is non-empty. `beats.txt` either contains ordered beats or is blank
  so LM Studio can generate one beat per segment before startup continues.

For the first test, use a short run and low resolution:

```powershell
python minimax.py 5 10 0.2
```

This requests two five-second segments at approximately 0.2 megapixels for the
initial clip.

## Running the program

The three main settings are positional arguments:

```text
python minimax.py SEGMENT_LENGTH TOTAL_LENGTH MEGAPIXELS [ff] [--resume SEGMENT] [--steps STEPS] [--context-frames FRAMES] [--refresh SEGMENTS] [--model {ministral,qwen}] [--lora LORA_NAME:STRENGTH ...]
```

Separate values with spaces as shown above. For convenience, commas are also
accepted, including both `python minimax.py 5, 10, .2` and
`python minimax.py 5,10,.2`.

| Argument | Meaning |
|---|---|
| `SEGMENT_LENGTH` | Target seconds generated per segment; must be greater than zero. |
| `TOTAL_LENGTH` | Target total movie length in seconds; must be greater than zero. |
| `MEGAPIXELS` | Initial and refresh workflow resolution target; must be greater than zero. |
| `--resume SEGMENT` | Continue at this one-based segment number; defaults to `1`. |
| `--steps STEPS` | BasicScheduler sampling steps for both workflows; defaults to `6`. |
| `--context-frames FRAMES` | Latent frames retained by `MiniMaxH3VideoExtendPatched`; defaults to `8` and supports values such as `2`, `4`, `8`, or `12`. |
| `--refresh SEGMENTS` | Enable auto refresh on every Nth segment using `Minimax_auto_refresh_API.json`; disabled by default. |
| `--model {ministral,qwen}` | Select the response formatter for the user-loaded LM Studio model; defaults to `ministral`. |
| `--lora LORA_NAME:STRENGTH` | Apply a global LoRA to every beat. Repeat the option for any number of ordered LoRAs. |
| `ff` or `--ff` | Add opening-frame instructions for `<Picture 1>` when generating segment 1; defaults to disabled. |

For example, this applies two global LoRAs to every segment; any LoRAs declared
on the active beat are added after them:

```powershell
python minimax.py 5 60 0.5 --lora style.safetensors:0.7 --lora motion.safetensors:0.35
```

### Example: new 60-second run

```powershell
python minimax.py 5 60 0.5
```

This creates 12 segments. Starting a new run with the default resume value of
`1` starts a new checkpoint and resets beat progress.

### Example: refresh every fifth segment

```powershell
python minimax.py 5 60 0.5 --refresh 5
```

Segments 5 and 10 use `Minimax_auto_refresh_API.json`. Before each refresh, the
program extracts the exact last frame of the preceding segment into the ComfyUI
input folder, assigns it to `Refresh First Frame`, copies all six reference-image
settings from the initial workflow, and prints an `AUTO REFRESH` notice. The
following segments return to the normal append workflow until the next multiple
of five. Segment 1 always uses the initial workflow.

### Example: resume at segment 12

Use the exact same first three values as the interrupted run:

```powershell
python minimax.py 5 60 0.5 --resume 12
```

Resume means segments 1–11 must already have successful checkpoint records.
The current command-line settings and source files may differ from the original
run; resume uses the ordered segment records, formatted director
results, and every prior video path. It restores beat completion, recent
director context, and the video chain used for final stitching. If `story.txt`,
`beats.txt`, or `subjects.txt` changed after the checkpoint, restore the
original inputs or start a new run.

## Generated files

| File or folder | Purpose |
|---|---|
| `generation_state.json` | Atomic checkpoint containing settings, director results, beat state, committed structured continuity state, internal video-created subject definitions, and video paths. |
| `beat_progress.txt` | Readable DONE/NEXT/TODO beat checklist. |
| ComfyUI `output/video/segment_*.mp4` | Individual generated clips. |
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
- A background LM Studio request proposes a structured continuity candidate for
  the current segment. It becomes authoritative only after ComfyUI successfully
  renders that segment.
- The next director request receives an authoritative opening state rendered
  directly from the last committed structured state and the two newest exact
  prompts, instead of an independently maintained prose summary. The outgoing
  MiniMax H3 prompt expresses it as a `<Video 1>` continuation block with
  `summary` and `retention_analysis` sections. It omits internal field labels
  and unknown `N/A` values.
- Prompt authority is ordered: BEAT STATE controls plot progression;
  AUTHORITATIVE OPENING STATE controls current physical continuity; SUBJECT
  REGISTRY controls identity and Picture mappings; recent generated segments
  are secondary context; and the source story supplies creative intent.
- The director sees the active beat and a configurable/dynamically bounded
  lookahead rather than the entire future beat list. Python retains the
  complete beat list for scheduling, completion validation, and checkpoints.
- Long source stories use a deterministic `CURRENT STORY CONTEXT` selected
  around the active beat, nearby lookahead, and registered subjects. When no
  reliable match exists, a bounded fallback is used without giving the source
  ending disproportionate authority.
- New checkpoints include a versioned `continuity_state` envelope alongside
  independently addressable environment, camera, subject position, pose,
  wardrobe, condition, props, ongoing action, audio, video-only subject ID, and
  subject-origin fields. Older
  checkpoints without that envelope are migrated automatically during resume.
- Continuity updates are candidates while a segment renders. They are committed
  only after the render succeeds; failed renders discard the candidate and keep
  the last successful segment's opening state.
- Beat completion is accepted only as a contiguous prefix of `beats.txt`, so a
  model cannot silently skip a required event.

Outgoing LM Studio requests are appended to `prompt_history.txt` as complete
JSON records. Each record includes a timestamp, response-format flag,
and any request metadata, followed by the exact normalized message batch.

## ComfyUI render retries

Each ComfyUI render attempt has a 15-minute wall-clock timeout. A completed
ComfyUI execution error or a render that remains pending past the timeout calls
`/free` to release VRAM and retries the segment, up to 10 retries.

For the initial workflow, each retry lowers the requested resolution by `0.02`
megapixels, for a maximum total reduction of `0.20` megapixels. The workflow
is rebuilt for every attempt, including a fresh random seed. Append segments
retry at the inherited resolution because their workflow has no resolution
selector. Failed attempts do not update `generation_state.json`; only a
successful render is checkpointed.

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

### ComfyUI runs out of memory or remains pending

The script automatically releases VRAM and retries completed execution errors
or 15-minute render timeouts. Initial-segment retries reduce the megapixel
target by `0.02` each time. After 10 retries, the program exits and reports the
last ComfyUI failure. Append-segment retries keep the previous video's
resolution.

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

- Resume settings and source files may differ from the original run.
- Do not move or rename completed segment files.
- Check `generation_state.json` for the first missing or moved segment video.

### Out of VRAM

- Lower the megapixel value.
- Shorten the segment length.
- Enable `low_vram` on the MiniMax-H3 Turbo LoRA node.
- Close other GPU-heavy applications.

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
| `Minimax_auto_refresh_API.json` | Auto-refresh reference-to-video workflow used by `--refresh`. |
| `story.txt` | Source story or creative brief. |
| `beats.txt` | Ordered story events; blank triggers automatic beat generation. |
| `subjects.txt` | Optional subject/reference definitions. |
| `stitch.bat` | Optional Windows-only FFmpeg concat helper. |
| `requirements.txt` | Python package requirements. |
