import json
import math
from fractions import Fraction

import node_helpers
import torch
from comfy_api.latest import InputImpl, Types, io

from .ltx_director_motion_brush_v2 import GuideData, _resize_image
from .ltx_director_guide import _load_motion_video_frames


_SYNTHETIC_DIRECTOR_ATTENTION_STRENGTH = 0.35
_MOTION_BOUNDARY_GUARD_FRAMES = 16
_MOTION_CARRY_MAX_FRAMES = 48
AnyData = io.Custom("*")


def _clamp01(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _motion_segment_carry_frames(seg: dict) -> int:
    try:
        return max(0, min(_MOTION_CARRY_MAX_FRAMES, int(round(float(seg.get("motionCarryFrames", 0) or 0)))))
    except (TypeError, ValueError):
        return 0


def _motion_segment_next_start(seg: dict) -> int | None:
    try:
        return int(round(float(seg.get("nextStart", seg.get("next_start")))))
    except (TypeError, ValueError):
        return None


def _normalise_point(point: dict, image_size: dict | None) -> dict[str, float]:
    x = float(point.get("x", 0.0))
    y = float(point.get("y", 0.0))
    if abs(x) <= 1.5 and abs(y) <= 1.5:
        return {"x": _clamp01(x), "y": _clamp01(y)}

    image_size = image_size or {}
    img_w = float(image_size.get("width") or image_size.get("w") or 1.0)
    img_h = float(image_size.get("height") or image_size.get("h") or 1.0)
    return {"x": _clamp01(x / max(1.0, img_w)), "y": _clamp01(y / max(1.0, img_h))}


def _positive_image_size(image_size: dict | None) -> tuple[float, float] | None:
    if not isinstance(image_size, dict):
        return None
    try:
        width = float(image_size.get("width") or image_size.get("w") or 0.0)
        height = float(image_size.get("height") or image_size.get("h") or 0.0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _snap_down_to_canvas(value: float, divisible_by: int, canvas_value: int) -> int:
    canvas_value = max(1, int(canvas_value))
    div = max(1, int(divisible_by or 1))
    raw = max(1, int(value))
    if div > 1:
        raw = max(div, (raw // div) * div)
    return max(1, min(canvas_value, raw))


def _transform_motion_point_for_resize(
    point: dict[str, float],
    image_size: dict | None,
    resize_method: str | None,
    canvas_width: int,
    canvas_height: int,
    resize_divisible_by: int = 1,
) -> dict[str, float]:
    """Map source-image brush coordinates onto the generated guide canvas."""

    method = (resize_method or "maintain aspect ratio").strip().lower()
    if method not in {"pad", "pad green", "crop"}:
        return {"x": _clamp01(point["x"]), "y": _clamp01(point["y"])}

    source_size = _positive_image_size(image_size)
    if source_size is None:
        return {"x": _clamp01(point["x"]), "y": _clamp01(point["y"])}

    src_w, src_h = source_size
    canvas_w = max(1, int(canvas_width))
    canvas_h = max(1, int(canvas_height))
    x = _clamp01(point["x"])
    y = _clamp01(point["y"])

    if method in {"pad", "pad green"}:
        ratio = min(canvas_w / src_w, canvas_h / src_h)
        inner_w = _snap_down_to_canvas(src_w * ratio, resize_divisible_by, canvas_w)
        inner_h = _snap_down_to_canvas(src_h * ratio, resize_divisible_by, canvas_h)
        pad_l = (canvas_w - inner_w) / 2.0
        pad_t = (canvas_h - inner_h) / 2.0
        mapped_x = (pad_l + x * max(0, inner_w - 1)) / max(1, canvas_w - 1)
        mapped_y = (pad_t + y * max(0, inner_h - 1)) / max(1, canvas_h - 1)
        return {"x": _clamp01(mapped_x), "y": _clamp01(mapped_y)}

    ratio = max(canvas_w / src_w, canvas_h / src_h)
    scaled_w = max(canvas_w, int(src_w * ratio))
    scaled_h = max(canvas_h, int(src_h * ratio))
    crop_l = (scaled_w - canvas_w) / 2.0
    crop_t = (scaled_h - canvas_h) / 2.0
    mapped_x = (x * max(0, scaled_w - 1) - crop_l) / max(1, canvas_w - 1)
    mapped_y = (y * max(0, scaled_h - 1) - crop_t) / max(1, canvas_h - 1)
    return {"x": _clamp01(mapped_x), "y": _clamp01(mapped_y)}


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


def _motion_segment_frame_counts(
    seg: dict,
    next_start: int | None,
    total_frames: int,
    boundary_guard_frames: int = _MOTION_BOUNDARY_GUARD_FRAMES,
) -> tuple[int, int]:
    start = int(round(float(seg.get("start", 0) or 0)))
    length = int(round(float(seg.get("length", 0) or 0)))
    if start >= total_frames or length < 0:
        return 0, 0

    seg_start = max(0, start)
    segment_end = max(seg_start, start + length)
    max_frames = max(0, total_frames - seg_start)
    if max_frames <= 0:
        return 0, 0

    sample_frames = max(1, length)
    render_frames = sample_frames

    if next_start is not None and int(next_start) <= segment_end:
        effective_guard = int(boundary_guard_frames or 0) - _motion_segment_carry_frames(seg)
        target_end = max(seg_start + 1, int(next_start) - effective_guard)
        render_frames = max(1, target_end - seg_start)
        sample_frames = max(sample_frames, render_frames)
    elif segment_end < total_frames:
        sample_frames += 1
        render_frames = sample_frames

    sample_frames = min(sample_frames, max_frames)
    render_frames = max(1, min(render_frames, sample_frames))
    return sample_frames, render_frames


def _motion_segment_local_frame_count(seg: dict, next_start: int | None, total_frames: int) -> int:
    _, render_frames = _motion_segment_frame_counts(seg, next_start, total_frames)
    return render_frames


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
            category="exportAnything/LTX Motion Brush",
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
                io.Video.Output("video", display_name="motion_guide_video"),
                AnyData.Output(
                    "video_any",
                    display_name="motion_guide_any",
                    tooltip="Wildcard copy of motion_guide_video for nodes that use ANY sockets.",
                ),
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

        sorted_segments = sorted(payload.get("segments", []), key=lambda s: int(float(s.get("start", 0) or 0)))
        for seg_idx, seg in enumerate(sorted_segments):
            if not isinstance(seg, dict):
                continue
            start = int(round(float(seg.get("start", 0) or 0)))
            next_start = _motion_segment_next_start(seg)
            if next_start is None:
                for next_seg in sorted_segments[seg_idx + 1 :]:
                    if not isinstance(next_seg, dict):
                        continue
                    try:
                        candidate = int(round(float(next_seg.get("start", 0) or 0)))
                    except (TypeError, ValueError):
                        continue
                    if candidate > start:
                        next_start = candidate
                        break

            sample_frames, render_frames = _motion_segment_frame_counts(seg, next_start, total_frames)
            if sample_frames <= 0 or render_frames <= 0:
                continue

            raw_tracks = seg.get("tracks", [])
            if not isinstance(raw_tracks, list) or not raw_tracks:
                continue

            image_size = seg.get("imageSize") if isinstance(seg.get("imageSize"), dict) else {}
            resize_method = seg.get("resizeMethod") or seg.get("resize_method") or "maintain aspect ratio"
            try:
                resize_divisible_by = int(round(float(seg.get("resizeDivisibleBy") or seg.get("resize_divisible_by") or 1)))
            except (TypeError, ValueError):
                resize_divisible_by = 1
            sampled_tracks = []
            for track in raw_tracks:
                if not isinstance(track, list) or not track:
                    continue
                points = []
                for point in track:
                    if not isinstance(point, dict) or "x" not in point or "y" not in point:
                        continue
                    normalised = _normalise_point(point, image_size)
                    points.append(
                        _transform_motion_point_for_resize(
                            normalised,
                            image_size,
                            resize_method,
                            width,
                            height,
                            resize_divisible_by,
                        )
                    )
                if not points:
                    continue
                sampled_tracks.append(_interpolate(points, sample_frames))

            if not sampled_tracks:
                continue

            segments_rendered += 1
            tracks_rendered += len(sampled_tracks)
            seg_start = max(0, start)
            for local_idx in range(render_frames):
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
        video = _video_from_frames(out, float(payload.get("frame_rate") or 24.0))
        return io.NodeOutput(out, 0, summary, video, video)


def _latent_output_shape(optional_latent, width: int, height: int, duration_frames: int) -> tuple[int, int, int]:
    latent_frames = 0
    if optional_latent is not None and isinstance(optional_latent, dict):
        samples = optional_latent.get("samples")
        if isinstance(samples, torch.Tensor) and samples.ndim == 5:
            latent_frames = int(samples.shape[2])
            if width <= 0:
                width = int(samples.shape[4]) * 32
            if height <= 0:
                height = int(samples.shape[3]) * 32

    if duration_frames <= 0 and latent_frames > 0:
        duration_frames = max(0, (latent_frames - 1) * 8)

    return max(0, int(duration_frames)), int(width), int(height)


def _video_from_frames(frames: torch.Tensor, frame_rate: float):
    fps = max(0.001, float(frame_rate or 24.0))
    return InputImpl.VideoFromComponents(
        Types.VideoComponents(
            images=frames,
            audio=None,
            frame_rate=Fraction(round(fps * 1000), 1000),
        )
    )


def _blank_retake_source_preview(
    width: int,
    height: int,
    total_frames: int,
    status: str,
    reason: str,
    start_frame: int,
    frame_rate: float,
) -> io.NodeOutput:
    width = width if width > 0 else 768
    height = height if height > 0 else 512
    total_frames = max(1, int(total_frames))
    out = torch.zeros(total_frames, int(height), int(width), 3, dtype=torch.float32)
    video = _video_from_frames(out, frame_rate)
    summary = json.dumps(
        {
            "version": 1,
            "status": status,
            "reason": reason,
            "source": "",
            "start_frame": int(start_frame),
            "frame_rate": float(frame_rate),
            "width": int(width),
            "height": int(height),
            "frames": int(total_frames),
        }
    )
    return io.NodeOutput(out, video, 0, summary, video)


class LTXDirectorMotionBrushV2RetakeSourcePreview(io.ComfyNode):
    """Decode the Retake Mode source video as an image batch for split-view comparison."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LTXDirectorMotionBrushV2RetakeSourcePreview",
            display_name="LTX Director Motion Brush V2 Retake Source Preview",
            category="exportAnything/LTX Motion Brush",
            description=(
                "Reads the Retake Mode video stored in LTX Director Motion Brush V2 guide_data "
                "and emits the same source range as an IMAGE batch for comparison nodes."
            ),
            inputs=[
                GuideData.Input(
                    "guide_data",
                    tooltip="Connect guide_data from LTX Director Motion Brush V2.",
                ),
                io.Latent.Input(
                    "optional_latent",
                    optional=True,
                    tooltip="Optional Director video latent. When connected, width, height, and frame count are inferred.",
                ),
                io.Int.Input("width", default=0, min=0, max=8192, step=8),
                io.Int.Input("height", default=0, min=0, max=8192, step=8),
                io.Int.Input(
                    "duration_frames",
                    default=0,
                    min=0,
                    max=10000,
                    step=1,
                    tooltip="0 uses guide_data duration or optional_latent length.",
                ),
                io.Combo.Input(
                    "resize_method",
                    options=["match director guide", "stretch to fit", "pad", "pad green", "crop"],
                    default="match director guide",
                    tooltip="How to resize the source video for comparison. The default mirrors the Director retake guide path.",
                ),
                io.Combo.Input(
                    "resample_mode",
                    options=["nearest", "linear"],
                    default="nearest",
                    tooltip="Frame resampling used when the source video FPS differs from the Director timeline FPS.",
                ),
                io.Combo.Input(
                    "on_missing",
                    options=["blank frame", "error"],
                    default="blank frame",
                    tooltip="Whether to return a black placeholder or raise an error when no Retake Mode source is available.",
                ),
            ],
            outputs=[
                io.Image.Output("image", display_name="retake_source_images"),
                io.Video.Output("video", display_name="retake_source_video"),
                io.Int.Output("frame_idx", display_name="frame_idx"),
                io.String.Output("render_summary"),
                AnyData.Output(
                    "video_any",
                    display_name="retake_source_any",
                    tooltip="Wildcard copy of retake_source_video for nodes that use ANY sockets.",
                ),
            ],
        )

    @classmethod
    def execute(
        cls,
        guide_data: dict,
        width: int,
        height: int,
        duration_frames: int,
        resize_method: str,
        resample_mode: str,
        on_missing: str,
        optional_latent=None,
    ) -> io.NodeOutput:
        guide_data = guide_data if isinstance(guide_data, dict) else {}
        try:
            timeline = json.loads(guide_data.get("timeline_data", "{}") or "{}")
        except Exception:
            timeline = {}

        frame_rate = float(guide_data.get("frame_rate", 24) or 24)
        start_frame = int(guide_data.get("start_frame", 0) or 0)
        guide_duration = int(guide_data.get("duration_frames", 0) or 0)
        if duration_frames <= 0:
            duration_frames = guide_duration
        duration_frames, width, height = _latent_output_shape(optional_latent, width, height, duration_frames)
        total_frames = max(1, int(duration_frames) + 1)

        retake_video = timeline.get("retakeVideo") if isinstance(timeline, dict) else None
        video_file = retake_video.get("imageFile", "") if isinstance(retake_video, dict) else ""
        missing_reason = ""
        if not timeline.get("retakeMode", False):
            missing_reason = "Retake Mode is not active in guide_data."
        elif retake_video and not video_file:
            missing_reason = "Retake Mode source video is still uploading or has no saved file path."
        elif not video_file:
            missing_reason = "No Retake Mode source video is saved in guide_data."

        if missing_reason:
            if on_missing == "error":
                raise ValueError(missing_reason)
            return _blank_retake_source_preview(
                width,
                height,
                total_frames,
                "missing",
                missing_reason,
                start_frame,
                frame_rate,
            )

        frames = _load_motion_video_frames(
            video_file,
            trim_start_frames=start_frame,
            length_frames=total_frames,
            director_fps=frame_rate,
            resample_mode=resample_mode,
        )

        source_height = int(frames.shape[1])
        source_width = int(frames.shape[2])
        target_width = width if width > 0 else source_width
        target_height = height if height > 0 else source_height
        effective_resize = resize_method
        if effective_resize == "match director guide":
            effective_resize = guide_data.get("resize_method", "maintain aspect ratio") or "maintain aspect ratio"
        if effective_resize == "maintain aspect ratio":
            effective_resize = "pad"

        pixels = _resize_image(
            frames[:, :, :, :3],
            int(target_width),
            int(target_height),
            effective_resize,
            divisible_by=1,
        )

        summary = json.dumps(
            {
                "version": 1,
                "status": "ok",
                "source": video_file,
                "start_frame": int(start_frame),
                "frame_rate": float(frame_rate),
                "resize_method": effective_resize,
                "width": int(pixels.shape[2]),
                "height": int(pixels.shape[1]),
                "frames": int(pixels.shape[0]),
            }
        )
        video = _video_from_frames(pixels, frame_rate)
        return io.NodeOutput(pixels, video, 0, summary, video)


def _conditioning_get_value(conditioning, key, default=None):
    for item in conditioning:
        if len(item) > 1 and key in item[1]:
            return item[1][key]
    return default


def _as_non_negative_int(value, default=0):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return default


def _guide_entry_frame_sum(entries) -> int:
    total = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        latent_shape = entry.get("latent_shape")
        if not isinstance(latent_shape, (list, tuple)) or not latent_shape:
            continue
        total += _as_non_negative_int(latent_shape[0])
    return total


def _keyframe_unique_frame_count(keyframe_idxs) -> int:
    if keyframe_idxs is None or not hasattr(keyframe_idxs, "shape") or len(keyframe_idxs.shape) < 3:
        return 0
    try:
        return int(torch.unique(keyframe_idxs[:, 0, :, 0]).shape[0])
    except Exception:
        return 0


def _normalise_guide_attention_entries(conditioning, director_attention_strength=None):
    keyframe_idxs = _conditioning_get_value(conditioning, "keyframe_idxs")
    existing = _conditioning_get_value(conditioning, "guide_attention_entries", [])
    entries = [*existing] if existing else []
    crop_frames = _as_non_negative_int(
        _conditioning_get_value(conditioning, "nghtdrp_guide_crop_latent_frames", 0)
    )
    keyframe_crop_frames = _keyframe_unique_frame_count(keyframe_idxs)
    guide_entry_crop_frames = _guide_entry_frame_sum(entries)

    keyframe_token_count = 0
    if keyframe_idxs is not None and hasattr(keyframe_idxs, "shape") and len(keyframe_idxs.shape) >= 3:
        keyframe_token_count = int(keyframe_idxs.shape[2])
    existing_token_count = sum(_as_non_negative_int(entry.get("pre_filter_count", 0)) for entry in entries)
    missing_token_count = keyframe_token_count - existing_token_count

    # LTX appends every guide latent to the end of the sampled latent. Director's
    # guide node records its own appended frame count, while a downstream
    # LTXAddVideoICLoRAGuide records attention entries but not the crop metadata
    # that DirectorCropGuides relies on between stages.
    if entries and missing_token_count > 0:
        effective_crop_frames = max(
            crop_frames + guide_entry_crop_frames,
            crop_frames,
            keyframe_crop_frames,
        )
    else:
        effective_crop_frames = max(
            crop_frames,
            guide_entry_crop_frames,
            keyframe_crop_frames,
        )

    values = {"nghtdrp_guide_crop_latent_frames": effective_crop_frames}
    if effective_crop_frames > crop_frames:
        print(
            "[LTXDirectorMotionBrushV2GuideAttention] "
            f"crop frames {crop_frames} -> {effective_crop_frames} "
            f"(keyframe={keyframe_crop_frames}, guide_entries={guide_entry_crop_frames}, "
            f"missing_tokens={max(0, missing_token_count)})"
        )

    if keyframe_token_count > 0 and entries and missing_token_count > 0:
        if director_attention_strength is None:
            director_attention_strength = _SYNTHETIC_DIRECTOR_ATTENTION_STRENGTH
        director_attention_strength = max(0.0, min(1.0, float(director_attention_strength)))
        synthetic_frame_count = max(1, crop_frames, keyframe_crop_frames - guide_entry_crop_frames)

        synthetic_director_entry = {
            "pre_filter_count": missing_token_count,
            # Regular Director keyframes need a bookkeeping entry so LTX can
            # partition guide tokens, but full attention here can overpower the
            # motion-track IC-LoRA and collapse the result back into still frames.
            "strength": director_attention_strength,
            "pixel_mask": None,
            # The first element is intentionally frame-like because some LTX
            # helpers use guide_attention_entries as a frame-count fallback.
            "latent_shape": [synthetic_frame_count, 1, max(1, missing_token_count)],
        }
        values["guide_attention_entries"] = [synthetic_director_entry, *entries]

    if effective_crop_frames == crop_frames and "guide_attention_entries" not in values:
        return conditioning

    return node_helpers.conditioning_set_values(conditioning, values)


class LTXDirectorMotionBrushV2GuideAttention(io.ComfyNode):
    """Reconcile IC-LoRA guide metadata after mixing Director keyframes and motion guides."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="LTXDirectorMotionBrushV2GuideAttention",
            display_name="LTX Director Motion Brush V2 Guide Attention",
            category="exportAnything/LTX Motion Brush",
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
            category="exportAnything/LTX Motion Brush",
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
    "LTXDirectorMotionBrushV2RetakeSourcePreview": LTXDirectorMotionBrushV2RetakeSourcePreview,
    "LTXDirectorMotionBrushV2GuideAttention": LTXDirectorMotionBrushV2GuideAttention,
    "LTXDirectorMotionBrushV2SafeDownscaleFactor": LTXDirectorMotionBrushV2SafeDownscaleFactor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LTXDirectorMotionBrushV2Guide": "LTX Director Motion Brush V2 Guide",
    "LTXDirectorMotionBrushV2RetakeSourcePreview": "LTX Director Motion Brush V2 Retake Source Preview",
    "LTXDirectorMotionBrushV2GuideAttention": "LTX Director Motion Brush V2 Guide Attention",
    "LTXDirectorMotionBrushV2SafeDownscaleFactor": "LTX Director Motion Brush V2 Safe Downscale Factor",
}
