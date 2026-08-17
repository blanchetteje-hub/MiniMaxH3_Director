# Minimax Video Generator Automation

An automated pipeline for generating continuous, story-driven videos using LLM (LM Studio) for narrative generation and ComfyUI for video synthesis. This system maintains character continuity, scene consistency, and beat progression across multiple video segments.

## Requirements

Before running the automation script, ensure you have the following components installed and configured:

### Python Environment
- **Python 3.8+** with the `requests` library installed
- Install required packages:
  ```bash
  pip install requests
  ```

### ComfyUI Installation & Nodes
- **[ComfyUI](https://github.com/comfyanonymous/ComfyUI)** (or [ComfyUI-frontend-portable](https://github.com/ltdrdata/ComfyUI-Installer)) properly installed and running
- **API Access**: ComfyUI must be started with API mode enabled (default at `http://127.0.0.1:8188`)

#### Required Custom Nodes
Install the following custom node packages via the ComfyUI manager or git clone to `ComfyUI/custom_nodes/`:
- **ComfyUI-Minimax-H3-Turbo**: Core workflow nodes for Minimax H3 Turbo video generation
- **ComfyUI-MiniMax-H3-Extend**: Extension nodes for video continuation and reference image handling

#### Required Video Helper Suite
Install the [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) custom nodes, specifically requiring the `VHS_LoadVideoPath` node for video stitching and continuity.

#### Required LoRA Models
Ensure the following LoRA model file is present in your ComfyUI models directory:
- **Down LoRA**: Place `minimax_h3_ref2v_turbo_4step_v0.1_comfyui.safetensors` in the appropriate models folder (typically under `models/loras/MiniMaxH3/minimax_h3_ref2v_turbo_4step_v0.1_comfyui.safetensors`)

#### Required VAEs and Models
Download the following VAE and model files to your ComfyUI models directory:
- **Main Model**: Place `minimax_h3_fl2va_pruned_int8_convrot.safetensors` in `models/diffusion_models` (or appropriate unet folder)
- **Audio VAE**: Place `minimax_h3_audio_vae_fp32.safetensors` in `models/vae/` (or appropriate VAE models folder)
- **Video VAE**: Place `minimax_h3_video_vae_fp16.safetensors` in `models/vae/` (or appropriate VAE models folder)
- **Qwen3VL Model**: Place `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` in your ComfyUI models directory (typically under `models/text_encoders/` or `models/checkpoints/` depending on your workflow configuration)

### LM Studio Setup
- **[LM Studio](https://lmstudio.ai)** installed and running with an LLM instance active
- **Local API Server**: Enable the local server in LM Studio (default port `1234`)
  - The server should be accessible at `http://192.168.0.203:1234` or your configured local IP/localhost
- **Supported Model Format**: Ensure the loaded model supports JSON schema structured output (as required by the director system prompt)

### System Requirements
- **FFmpeg**: Installed and available in your system PATH for video trimming and stitching operations
  - On Windows: Download from [FFmpeg](https://ffmpeg.org/download.html) and add `bin/` to your system PATH, or use a package manager like `choco install ffmpeg` or `scoop install ffmpeg`
- **GPU Memory**: Sufficient VRAM for ComfyUI video generation (adjust megapixels and segment length if experiencing out-of-memory errors)

### Required Configuration Files
Ensure the following files exist in the automation directory:
- `story.txt` - The source narrative/story to be adapted into video format
- `beats.txt` - Defined story beats that guide the narrative progression
- `subject_definitions.txt` (optional) - Character appearance references and persistent traits
- `Minimax_auto_API.json` - ComfyUI workflow for generating the first segment. Images will need to be updated for nodes 114, 116, 120, 137
- `Minimax_auto_append_API.json` - ComfyUI workflow for appending subsequent segments. Images will need to be updated for nodes 114, 116, 120, 137

#### Required Files in ComfyUI Output Directory
The following files must be placed in your **ComfyUI output directory** (typically the `output/` or `./output/` folder where ComfyUI saves generated videos):
- `list.txt` - List file used by the stitching script to identify and process generated video files (the script will automatically do this, you can edit it yourself and run stitch.bat if needed)
- `stitch.bat` - Batch script for concatenating/stitching generated video segments into a final continuous video

## Overview

This tool automates the creation of multi-segment videos by:
1. Parsing a source story and predefined "story beats"
2. Using an LLM (via LM Studio) to generate segment-by-segment director instructions
3. Passing those instructions to ComfyUI workflows for video generation
4. Maintaining continuity memory across segments for visual consistency
5. Stitching all generated segments into a final continuous video

## Configuration Files

The system relies on several configuration and data files:

### Required Input Files
- `story.txt` - The source narrative/story to be adapted into video format
- `beats.txt` - Defined story beats that guide the narrative progression
- `subject_definitions.txt` (optional) - Character appearance references and persistent traits

### Workflow Files
- `initial_workflow.json` / `Minimax_auto_API.json` - ComfyUI workflow for generating the first segment
- `append_workflow.json` / `Minimax_auto_append_API.json` - ComfyUI workflow for appending subsequent segments

### Output & State Files
- `beat_progress.txt` - Tracks which story beats have been completed
- `continuity_memory.txt` - Maintains visual and narrative continuity across segments
- `state.json` (or similar) - Stores generation state for resume capabilities

## Key Features

### Segment-Based Generation
- Configurable segment length and total video duration
- Automatic calculation of required segments
- Each segment corresponds to a specific "shot" with camera instructions

### Continuity Memory System
- Compacts narrative and visual information across completed segments
- Automatically folds older segments into summary memory after a configurable threshold
- Maintains character appearances, clothing, injuries, damage, props, and appearance changes

### Story Beat Tracking
- Maps generated segments to predefined story beats
- Tracks progress in real-time
- Validates completion of all required narrative moments

### Resume Capability
- Can resume generation from any segment if interrupted
- Preserves generated videos and continuity memory
- Maintains beat progress state

### Background Continuity Updates
- Uses ThreadPoolExecutor to run LLM continuity summaries while ComfyUI renders
- Overlaps LM Studio summary calls with GPU generation for efficiency

## Usage

### Basic Execution

```bash
python minimax.py --segment-length <seconds> --total-length <seconds> --megapixels <value> [--resume <segment-number>]
```

### Command Line Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `--segment-length` | Duration of each video segment in seconds | Yes |
| `--total-length` | Total target video duration in seconds | Yes |
| `--megapixels` | Target resolution for generated videos | Yes |
| `--resume` | Segment number to resume from (if > 1) | No (defaults to 1 = new run) |

### Example: New Generation

```bash
python minimax.py --segment-length 5 --total-length 60 --megapixels 0.5
```

### Example: Resume Generation

```bash
python minimax.py --segment-length 5 --total-length 60 --resume 12
```

## Director System Prompt Architecture

The LLM director system uses a structured prompt that enforces:

### Subject Persistence
- Pictures 1-4 serve as persistent appearance references
- Names and corresponding `<Picture N>` tags are preserved
- Persistent clothing, injuries, damage, props, and appearance changes are maintained

### Shot and Timing Rules
- Each segment contains exactly one shot
- Integrated multimodal descriptions must begin with continuation or cut camera declarations
- Timestamps use the current clip's local timeline (never cumulative movie timestamps)
- Shots divisible by 3 begin with hard camera cuts (CUT camera shots)

### Camera Declarations
Every shot explicitly states its camera setup:
1. **CONTINUATION**: `[Shot N] Camera continues from the previous shot, maintaining the established framing/angle/movement.`
2. **CUT**: `[Shot N] Camera cuts to a new shot: [briefly describe framing, angle, and position].`

### Dialogue Formatting
- Exact dialogue only (no generic speech descriptions)
- Format: `Character Name (S1) says: <d>[English] Actual spoken words.</d>`
- Speaker IDs must be consistent

### Lighting and Sound
- Lighting described only when triggered by action (e.g., opening curtains)
- Overall soundscape: 1-4 concise sentences of ambience and physical sounds
- Non-diegetic music: N/A unless background music materially benefits the scene

## Workflow Validation

Before generation begins, the system validates:

1. **Initial workflow file** is readable and valid
2. **Append workflow file** contains required nodes (72, 81, 87, 118, 114, 116, 120, 137, 139, 140, 142, 143)
3. **Image batch references** correctly map to subject images:
   - `image_1`: node "114", port 0
   - `image_2`: node "116", port 0
   - `image_3`: node "120", port 0
   - `image_4`: node "137", port 0
4. **Video load node** (143) is of type `VHS_LoadVideoPath`

## Generation Loop Flow

For each segment:

1. **LLM Director Request**: Generate segment description and identify completed beats
2. **Prompt Construction**: Build the H3 prompt with subject definitions included
3. **Workflow Preparation**: Select initial or append workflow based on segment number
4. **ComfyUI Queue**: Submit workflow for video generation
5. **Background Continuity Update**: If applicable, fold older segments into summary memory
6. **Wait for Completion**: Monitor ComfyUI until video is generated
7. **Validate Output**: Check video resolution and megapixels
8. **Update State**: Save generated video path, update beat progress, save generation state
9. **VRAM Management**: Free VRAM every 5 segments to prevent memory exhaustion

## Finalization

When all segments are complete:

1. **Final VRAM Cleanup**: Release remaining GPU memory
2. **Beat Validation**: Report any unfinished required story beats
3. **Video Stitching**: Concatenate all generated segments into a single continuous video

## Technical Notes

### Token Budget Management
- LLM input context is capped at `LLM_INPUT_TOKEN_BUDGET`
- Recent exact segments are included in full, older ones are summarized
- Context usage is reported before each LLM call

### Concurrency
- A single background worker handles continuity summary updates
- This ensures ordered continuity memory (each new compact memory depends on the previous)
- Overlaps LM Studio continuity calls with ComfyUI GPU generation

### State Preservation
After each successful segment:
- Generated video paths are appended to the state
- Beat progress is saved and displayed
- Continuity memory is updated and persisted
- Generation state is checkpointed for resume safety

## Troubleshooting

### Resume Failures
If a resume fails due to missing state files:
- Ensure `beat_progress.txt`, `continuity_memory.txt`, and state files exist
- Verify the beats signature matches the current `beats.txt`
- Check that the resume segment number does not exceed total segments

### Missing Workflow Nodes
If workflow validation fails:
- Verify append workflow contains all required nodes
- Check node ID mappings for subject images
- Ensure node 143 is a `VHS_LoadVideoPath` type

### VRAM Exhaustion
If generation fails due to GPU memory:
- The system automatically frees VRAM every 5 segments
- Consider reducing megapixels or segment length
- Close other GPU-intensive applications during generation

## Files Reference

| File | Purpose |
|------|---------|
| `minimax.py` | Main automation script |
| `story.txt` | Source narrative |
| `beats.txt` | Story beat definitions |
| `subject_definitions.txt` | Character appearance references |
| `beat_progress.txt` | Generated beat completion tracking |
| `continuity_memory.txt` | Narrative and visual continuity summary |
| `Minimax_auto_API.json` | Initial ComfyUI workflow |
| `Minimax_auto_append_API.json` | Append ComfyUI workflow |
