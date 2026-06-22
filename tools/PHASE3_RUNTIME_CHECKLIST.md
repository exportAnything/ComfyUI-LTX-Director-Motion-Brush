# Phase 3 Runtime Checklist

Use this after `tools/verify_phase3_local.py` passes. These checks require a
real ComfyUI browser session and the actual LTX models/workflow.

## Preflight

- Start ComfyUI normally.
- Hard refresh the browser after startup.
- Load the current Motion Brush V2 workflow.
- Confirm the node list includes:
  - `LTX Director Motion Brush V2`
  - `LTX Director Motion Brush V2 Guide`
  - `LTX Director Motion Brush V2 Guide Attention`
  - `LTX Director Motion Brush V2 Safe Downscale Factor`
  - `LTX Director Motion Brush V2 Director Guide`
  - `LTX Director Motion Brush V2 Crop Guides`

## Image And Matte Motion Brush

- Add at least one image segment in normal timeline mode.
- Draw one or more Motion Brush tracks on the image segment.
- Add a Matte Clip, select a matte color, and draw one or more Motion Brush tracks on the matte clip.
- Run the known-good Motion Brush workflow.
- Expected: generated video follows the drawn image-segment and matte-clip tracks.
- Expected: sparse-track preview shows only the intended colored control tracks.

## Retake Mode

- Enable `Retake Mode (BETA)`.
- Add a retake video.
- Run a short retake edit with the intended LoRA setup.
- Expected: Retake Mode remains video-focused and does not emit Motion Brush tracks.
- Expected: the retake result edits the selected video region instead of using the image Motion Brush guide.

## Video Plus Motion Brush Guard

- Return to normal timeline mode.
- Create a workflow state with at least one normal timeline video segment and at least one image or matte clip with Motion Brush tracks.
- Expected: the Motion Brush panel warns that Motion Brush supports image and matte clips only.
- Run generation.
- Expected: generation stops early with a clear error telling the user to remove normal timeline video segments, clear Motion Brush tracks, or use Retake Mode.

## Out Of Scope For Phase 3

- Workspace folder and chunked upload route changes.
- Motion Brush over video segments in the normal timeline.
- Training/model changes.
