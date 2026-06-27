# Changelog

## Unreleased

- Add lower-VRAM and GGUF lower-VRAM example workflows.
- Document `ComfyUI-GGUF` as an optional dependency for the GGUF workflow.

## 0.1.1

- Exclude development-only verification scripts from the Comfy Registry install archive.
- Clarify that verification helpers are available from a source checkout, not the Registry package.

## 0.1.0 Nightly

- Package the known-good LTX Director Motion Brush V2 workflow for GitHub prerelease testing.
- Rebrand package metadata for `exportAnything`.
- Add a sanitized public workflow at `example_workflows/LTX_Director_Motion_Brush_V2.json`.
- Add unique `exportanything_ltx_director_*` upload/audio/workspace routes for self-contained installs.
- Store new uploads under `ComfyUI/input/exportanything`.
- Preserve fallback reads for old `ComfyUI/input/whatdreamscost` media references.
- Document required custom nodes, models, and included Motion Brush nodes.
- Add explicit attribution for WhatDreamsCost and the upstream LTX Director v2 work.
- Expand README positioning to describe the rebuilt Motion Brush edition, helper nodes, retake preview, motion carry, upload routing, and guardrails.
- Add generated sample outputs under `Samples/`.
- Add lightweight GIF previews for GitHub README rendering.
- Prepare first Comfy Registry package under `ltx-director-motion-brush`.
