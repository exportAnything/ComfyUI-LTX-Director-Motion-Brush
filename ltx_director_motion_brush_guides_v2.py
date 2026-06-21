import json
import math

import node_helpers
import torch
from comfy_api.latest import io


_SYNTHETIC_DIRECTOR_ATTENTION_STRENGTH = 0.35


def _clamp01(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _normalise_point(point: dict, image_size: dict | None) -> dict[str, float]:
    x = float(point.get("x", 0.0))
    y = float(point.get("y", 0.0))
    if abs(x) <= 1.5 and abs(y) <= 1.5:
        return {"x": _clamp01(x), "y": _clamp01(y)}

    image_size = image_size or {}
    img_w = float(image_size.get("width") or image_size.get("w") or 1.0)
    img_h = float(image_size.get("height") or image_size.get("h") or 1.0)
    return {"x": _clamp01(x / max(1.0, img_w)), "y": _clamp01(y / max(1.0, img_h))}


def _catmull_rom(p0: dict, p1: dict, p2: dict, p3: dict, t: float) -> dict[str, float]:
    t2 = t * t
    t3 = t2 * t
    return {
        "x": 0.5
        * (
            2 * p1["x"]
            + (-p0["x"] + p2["x"]) * t
            + (2 * p0["x"] - 5 * p1["x"] + 4 * p2["x"] - p3["x"]) * t2
            + (-p0["x"] + 3 * p1["x"] - 3 * p2["x"] + p3["x"]) * t3
        ),
        "y": 0.5
        * (
            2 * p1["y"]
            + (-p0["y"] + p2["y"]) * t
            + (2 * p0["y"] - 5 * p1["y"] + 4 * p2["y"] - p3["y"]) * t2
            + (-p0["y"] + 3 * p1["y"] - 3 * p2["y"] + p3["y"]) * t3
        ),
    }


def _interpolate(points: list[dict], num_samples: int) -> list[dict[str, float]]:
    num_samples = max(1, int(num_samples))
    if not points:
        return []
    if len(points) == 1:
        return [points[0] for _ in range(num_samples)]
    if num_samples == 1:
        return [points[0]]
    if len(points) == 2:
        a, b = points
        return [
            {
                "x": a["x"] + (b["x"] - a["x"]) * i / (num_samples - 1),
                "y": a["y"] + (b["y"] - a["y"]) * i / (num_samples - 1),
            }
            for i in range(num_samples)
        ]

    padded = [points[0], *points, points[-1]]
    segment_count = len(padded) - 3
    result = []
    for i in range(num_samples):
        global_t = (i / (num_samples - 1)) * segment_count
        segment = min(int(global_t), segment_count - 1)
        local_t = global_t - segment
        result.append(
            _catmull_rom(
                padded[segment],
                padded[segment + 1],
                padded[segment + 2],
                padded[segment + 3],
                local_t,
            )
        )
    return result


def _parse_motion_payload(raw: str, fallback_duration: int) -> dict:
    try:
        payload = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}

    if isinstance(payload, list):
        payload = {
            "version": 1,
            "duration_frames": fallback_duration,
            "segments": [{"start": 0, "length": fallback_duration, "tracks": payload}],
        }

    if not isinstance(payload, dict):
        payload = {}

    payload.setdefault("version", 1)
    payload.setdefault("duration_frames", fallback_duration)
    payload.setdefault("segments", [])
    if not isinstance(payload["segments"], list):
        payload["segments"] = []
    return payload


def _age_color(ratio: float, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    ratio = max(0.0, min(1.0, float(ratio)))
    if ratio <= 1 / 3:
        t = ratio * 3
        color = (0.0, t, 1.0 - t)
    elif ratio <= 2 / 3:
        t = (ratio - 1 / 3) * 3
        color = (t, 1.0, 0.0)
    else:
        t = (ratio - 2 / 3) * 3
        color = (1.0, 1.0 - t, 0.0)
    return torch.tensor(color, device=device, dtype=dtype)


def _stamp_circle(
    frame: torch.Tensor,
    x: float,
    y: float,
    radius: float,
    color: torch.Tensor,
) -> None:
    height, width, _ = frame.shape
    cx = int(round(x))
    cy = int(round(y))
    r = max(1, int(math.ceil(radius)))
    x0 = max(0, cx - r)
    x1 = min(width, cx + r + 1)
    y0 = max(0, cy - r)
    y1 = min(height, cy + r + 1)
    if x0 >= x1 or y0 >= y1:
        return

    yy, xx = torch.meshgrid(
        torch.arange(y0, y1, device=frame.device),
        torch.arange(x0, x1, device=frame.device),
        indexing="ij",
    )
    mask = (xx - cx).float().square() + (yy - cy).float().square() <= radius * radius
    patch = frame[y0:y1, x0:x1]
    patch[mask] = color


class LTXDirectorMotionBrushV2Guide(io.ComfyNode):
    """Render per-keyframe Director Motion Brush data as an IC-LoRA guide video."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LTXDirectorMotionBrushV2Guide",
            display_name="LTX Director Motion Brush V2 Guide",
            category="WhatDreamsCost",
            description=(
                "Renders motion tracks saved by LTX Director Motion Brush into a sparse-track "
                "control video that can be connected to LTXAddVideoICLoRAGuide."
            ),
            inputs=[
                io.String.Input(
                    "motion_tracks",
                    multiline=True,
                    default='{"version":1,"duration_frames":120,"segments":[]}',
                    tooltip="Motion track JSON emitted by LTX Director Motion Brush.",
                ),
                io.Latent.Input(
                    "optional_latent",
                    optional=True,
                    tooltip="Optional Director video latent. When connected, width, height, and frame count are inferred if the explicit values are 0.",
                ),
                io.Int.Input("width", default=768, min=0, max=8192, step=8),
                io.Int.Input("height", default=512, min=0, max=8192, step=8),
                io.Int.Input(
                    "duration_frames",
                    default=0,
                    min=0,
                    max=10000,
                    step=1,
                    tooltip="Timeline duration excluding the final endpoint. 0 uses the Director payload or optional latent.",
                ),
                io.Int.Input("trail_frames", default=50, min=0, max=500, step=1),
                io.Int.Input("min_radius", default=2, min=1, max=64, step=1),
                io.Int.Input("max_radius", default=8, min=1, max=128, step=1),
            ],
            outputs=[
                io.Image.Output("image", display_name="motion_guide"),
                io.Int.Output("frame_idx", display_name="frame_idx"),
                io.String.Output("render_summary"),
            ],
        )

    @classmethod
    def execute(
        cls,
        motion_tracks: str,
        width: int,
        height: int,
        duration_frames: int,
        trail_frames: int,
        min_radius: int,
        max_radius: int,
        optional_latent=None,
    ) -> io.NodeOutput:
        latent_frames = 0
        if optional_latent is not None and isinstance(optional_latent, dict):
            samples = optional_latent.get("samples")
            if isinstance(samples, torch.Tensor) and samples.ndim == 5:
                latent_frames = int(samples.shape[2])
                if width <= 0:
                    width = int(samples.shape[4]) * 32
                if height <= 0:
                    height = int(samples.shape[3]) * 32

        inferred_duration = (latent_frames - 1) * 8 if latent_frames > 0 else 120
        fallback_duration = duration_frames if duration_frames > 0 else inferred_duration
        payload = _parse_motion_payload(motion_tracks, fallback_duration)

        payload_duration = int(payload.get("duration_frames") or fallback_duration)
        if duration_frames <= 0:
            duration_frames = payload_duration

        width = width if width > 0 else 768
        height = height if height > 0 else 512
        total_frames = max(1, int(duration_frames) + 1)

        device = torch.device("cpu")
        out = torch.zeros(total_frames, int(height), int(width), 3, dtype=torch.float32, device=device)
        segments_rendered = 0
        tracks_rendered = 0

        for seg in sorted(payload.get("segments", []), key=lambda s: int(float(s.get("start", 0) or 0))):
            if not isinstance(seg, dict):
                continue
            start = int(round(float(seg.get("start", 0) or 0)))
            length = int(round(float(seg.get("length", 0) or 0)))
            if start >= total_frames or length < 0:
                continue
            local_frames = min(max(1, length + 1), total_frames - max(0, start))
            if local_frames <= 0:
                continue

            raw_tracks = seg.get("tracks", [])
            if not isinstance(raw_tracks, list) or not raw_tracks:
                continue

            image_size = seg.get("imageSize") if isinstance(seg.get("imageSize"), dict) else {}
            sampled_tracks = []
            for track in raw_tracks:
                if not isinstance(track, list) or not track:
                    continue
                points = [
                    _normalise_point(point, image_size)
                    for point in track
                    if isinstance(point, dict) and "x" in point and "y" in point
                ]
                if not points:
                    continue
                sampled_tracks.append(_interpolate(points, local_frames))

            if not sampled_tracks:
                continue

            segments_rendered += 1
            tracks_rendered += len(sampled_tracks)
            seg_start = max(0, start)
            for local_idx in range(local_frames):
                frame_idx = seg_start + local_idx
                if frame_idx >= total_frames:
                    break
                trail_start = max(0, local_idx - int(trail_frames))
                for track in sampled_tracks:
                    for point_idx in range(trail_start, local_idx + 1):
                        if point_idx >= len(track):
                            continue
                        age = local_idx - point_idx
                        ratio = 1.0 if trail_frames <= 0 else 1.0 - (age / max(1, trail_frames))
                        radius = float(min_radius) + (float(max_radius) - float(min_radius)) * ratio
                        color = _age_color(ratio, out.device, out.dtype)
                        point = track[point_idx]
                        _stamp_circle(
                            out[frame_idx],
                            _clamp01(point["x"]) * (width - 1),
                            _clamp01(point["y"]) * (height - 1),
                            radius,
                            color,
                        )

        # Match LTXVDrawTracks' channel order for IC-LoRA motion-track conditioning.
        out = out[..., [2, 1, 0]]
        summary = json.dumps(
            {
                "version": 1,
                "width": int(width),
                "height": int(height),
                "frames": int(total_frames),
                "segments_rendered": int(segments_rendered),
                "tracks_rendered": int(tracks_rendered),
            }
        )
        return io.NodeOutput(out, 0, summary)


def _conditioning_get_value(conditioning, key, default=None):
    for item in conditioning:
        if len(item) > 1 and key in item[1]:
            return item[1][key]
    return default


def _normalise_guide_attention_entries(conditioning, director_attention_strength=None):
    keyframe_idxs = _conditioning_get_value(conditioning, "keyframe_idxs")
    if keyframe_idxs is None or not hasattr(keyframe_idxs, "shape") or len(keyframe_idxs.shape) < 3:
        return conditioning

    keyframe_token_count = int(keyframe_idxs.shape[2])
    if keyframe_token_count <= 0:
        return conditioning

    existing = _conditioning_get_value(conditioning, "guide_attention_entries", [])
    if not existing:
        return conditioning

    entries = [*existing]
    existing_token_count = sum(int(entry.get("pre_filter_count", 0) or 0) for entry in entries)
    missing_token_count = keyframe_token_count - existing_token_count
    if missing_token_count <= 0:
        return conditioning
    if director_attention_strength is None:
        director_attention_strength = _SYNTHETIC_DIRECTOR_ATTENTION_STRENGTH
    director_attention_strength = max(0.0, min(1.0, float(director_attention_strength)))

    synthetic_director_entry = {
        "pre_filter_count": missing_token_count,
        # Regular Director keyframes need a bookkeeping entry so LTX can
        # partition guide tokens, but full attention here can overpower the
        # motion-track IC-LoRA and collapse the result back into still frames.
        "strength": director_attention_strength,
        "pixel_mask": None,
        # The latent_shape is only consumed when pixel_mask is present, but keep a
        # valid shape for code paths that use entries to count guide frames.
        "latent_shape": [1, 1, missing_token_count],
    }
    return node_helpers.conditioning_set_values(
        conditioning,
        {"guide_attention_entries": [synthetic_director_entry, *entries]},
    )


class LTXDirectorMotionBrushV2GuideAttention(io.ComfyNode):
    """Reconcile IC-LoRA guide metadata after mixing Director keyframes and motion guides."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LTXDirectorMotionBrushV2GuideAttention",
            display_name="LTX Director Motion Brush V2 Guide Attention",
            category="WhatDreamsCost",
            description=(
                "Adds a synthetic guide-attention entry for regular Director keyframes while "
                "preserving the motion IC-LoRA guide entry. This avoids mixed-guide token "
                "count validation errors without disabling motion-track conditioning."
            ),
            inputs=[
                io.Conditioning.Input("positive"),
                io.Conditioning.Input("negative"),
                io.Float.Input(
                    "director_attention_strength",
                    default=_SYNTHETIC_DIRECTOR_ATTENTION_STRENGTH,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    tooltip=(
                        "How strongly regular Director still-image keyframes compete with "
                        "the motion IC-LoRA guide. Higher values preserve source images more; "
                        "lower values leave more room for motion."
                    ),
                ),
            ],
            outputs=[
                io.Conditioning.Output("positive"),
                io.Conditioning.Output("negative"),
            ],
        )

    @classmethod
    def execute(cls, positive, negative, director_attention_strength=_SYNTHETIC_DIRECTOR_ATTENTION_STRENGTH) -> io.NodeOutput:
        return io.NodeOutput(
            _normalise_guide_attention_entries(positive, director_attention_strength),
            _normalise_guide_attention_entries(negative, director_attention_strength),
        )


class LTXDirectorMotionBrushV2SafeDownscaleFactor(io.ComfyNode):
    """Clamp IC-LoRA reference downscale when the current latent grid cannot be dilated."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LTXDirectorMotionBrushV2SafeDownscaleFactor",
            display_name="LTX Director Motion Brush V2 Safe Downscale Factor",
            category="WhatDreamsCost",
            description=(
                "Passes through the IC-LoRA latent_downscale_factor when the latent width "
                "and height are divisible by it. Falls back to 1.0 for odd or otherwise "
                "incompatible latent grids to avoid LTXAddVideoICLoRAGuide dilation errors."
            ),
            inputs=[
                io.Latent.Input("latent"),
                io.Float.Input("requested_factor", default=1.0, min=1.0, max=10.0, step=1.0),
                io.Float.Input("fallback_factor", default=1.0, min=1.0, max=10.0, step=1.0),
            ],
            outputs=[
                io.Float.Output("latent_downscale_factor"),
                io.String.Output("summary"),
            ],
        )

    @classmethod
    def execute(cls, latent, requested_factor, fallback_factor=1.0) -> io.NodeOutput:
        requested = float(requested_factor or 1.0)
        fallback = float(fallback_factor or 1.0)
        effective = max(1.0, fallback)
        reason = "fallback"
        latent_width = 0
        latent_height = 0

        samples = latent.get("samples") if isinstance(latent, dict) else None
        if isinstance(samples, torch.Tensor) and samples.ndim == 5:
            latent_height = int(samples.shape[3])
            latent_width = int(samples.shape[4])
            requested_int = int(round(requested))
            fallback_int = int(round(fallback))
            if requested <= 1.0:
                effective = 1.0
                reason = "requested_factor_is_1"
            elif abs(requested - requested_int) > 1e-6:
                effective = 1.0
                reason = "requested_factor_not_integer"
            elif latent_width % requested_int == 0 and latent_height % requested_int == 0:
                effective = float(requested_int)
                reason = "requested_factor_compatible"
            elif (
                fallback_int > 1
                and latent_width % fallback_int == 0
                and latent_height % fallback_int == 0
            ):
                effective = float(fallback_int)
                reason = "fallback_factor_compatible"
            else:
                effective = 1.0
                reason = "latent_grid_not_divisible"
        else:
            effective = requested
            reason = "latent_shape_unavailable"

        summary = json.dumps(
            {
                "requested_factor": requested,
                "effective_factor": effective,
                "fallback_factor": fallback,
                "latent_width": latent_width,
                "latent_height": latent_height,
                "reason": reason,
            }
        )
        return io.NodeOutput(float(effective), summary)


NODE_CLASS_MAPPINGS = {
    "LTXDirectorMotionBrushV2Guide": LTXDirectorMotionBrushV2Guide,
    "LTXDirectorMotionBrushV2GuideAttention": LTXDirectorMotionBrushV2GuideAttention,
    "LTXDirectorMotionBrushV2SafeDownscaleFactor": LTXDirectorMotionBrushV2SafeDownscaleFactor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LTXDirectorMotionBrushV2Guide": "LTX Director Motion Brush V2 Guide",
    "LTXDirectorMotionBrushV2GuideAttention": "LTX Director Motion Brush V2 Guide Attention",
    "LTXDirectorMotionBrushV2SafeDownscaleFactor": "LTX Director Motion Brush V2 Safe Downscale Factor",
}
