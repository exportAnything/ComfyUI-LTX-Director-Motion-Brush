# LTX Director Motion Brush

Nightly ComfyUI nodes for LTX 2.3 timeline generation with per-image motion brush control.

This package is a fork of the LTX Director v2 work from WhatDreamsCost, with an added Motion Brush workflow for LTX 2.3 IC-LoRA motion-track control. It is intended as an early tester build, not a stable Comfy Registry release yet.

## Nightly Status

Nightly means this is the fast-moving preview channel. It is meant for users who are comfortable testing new ComfyUI nodes, reading notes, and reporting workflow-level issues.

The first release target is a GitHub prerelease tag named like:

```text
nightly-YYYYMMDD
```

## Install

Clone this repo into your ComfyUI `custom_nodes` folder:

```powershell
cd C:\ComfyUI\app\custom_nodes
git clone https://github.com/exportAnything/ComfyUI-LTX-Director-Motion-Brush.git
```

Restart ComfyUI after installing or updating.

This package can coexist with the upstream WhatDreamsCost LTX Director v2 package because Motion Brush uses unique node names and unique upload routes.

## Included Nodes

The public workflow depends on these nodes from this package:

- `LTXDirectorMotionBrushV2`
- `LTXDirectorMotionBrushV2Guide`
- `LTXDirectorMotionBrushV2GuideAttention`
- `LTXDirectorMotionBrushV2RetakeSourcePreview`
- `LTXDirectorMotionBrushV2SafeDownscaleFactor`
- `LTXDirectorMotionBrushV2DirectorGuide`
- `LTXDirectorMotionBrushV2CropGuides`

Existing node class names are kept stable so saved workflows continue to load.

## Required Custom Nodes

Install or update these separately:

- `ComfyUI-LTXVideo`
- `comfyui-kjnodes`
- `ComfyUI-Impact-Pack`

The example workflow also uses ComfyUI core video nodes and grouped/subgraph nodes saved inside the workflow.

## Required Models

The workflow expects an LTX 2.3 setup compatible with your local ComfyUI install. Typical required assets include:

- LTX 2.3 model/checkpoint or UNet setup used by your workflow.
- LTX 2.3 text encoders.
- LTX 2.3 VAE or tiny VAE used by the workflow.
- LTX 2.3 latent upscale model used by the workflow.
- IC-LoRA motion-track control LoRA, for example `ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors`.

Model paths are not bundled. Place models where your LTXVideo workflow expects them.

## Example Workflow

Load:

```text
example_workflows/LTX_Director_Motion_Brush_V2.json
```

The template is sanitized for release:

- no local user paths,
- no bundled source media,
- no saved retake video sample,
- package IDs updated to `ComfyUI-LTX-Director-Motion-Brush`.

## Motion Brush Notes

- Turn on `Motion Brush` before editing motion tracks.
- `resize_method` is locked to `maintain aspect ratio` while Motion Brush is active.
- `Guide Strength` on the timeline image affects how strongly that image is held.
- `Carry Motion` defaults to `0` for anti-bleed behavior.
- Intentional carry values can push one image's motion into the next image for transition effects.
- Retake Mode enforces a 6 second minimum selection.

## Upload Storage

New timeline uploads are stored under:

```text
ComfyUI/input/exportanything
```

Legacy workflows that reference `ComfyUI/input/whatdreamscost` media are still readable as a compatibility fallback.

## Verification

From this repo folder, run:

```powershell
C:\ComfyUI\.venv\Scripts\python.exe .\tools\verify_phase3_local.py
```

For a running ComfyUI server, add:

```powershell
C:\ComfyUI\.venv\Scripts\python.exe .\tools\verify_phase3_local.py --base-url http://127.0.0.1:8188
```

The local check covers motion payload guardrails, node registration, Python compile, frontend syntax, `pip check`, and whitespace errors.

## Credits

Original LTX Director v2 concept and implementation by WhatDreamsCost:

```text
https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI
```

Motion Brush packaging and LTX 2.3 motion-track integration by exportAnything.

See `ATTRIBUTION.md` for details.
