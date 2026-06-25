"""Verify Phase 3 motion-brush payload guardrails.

This is intentionally narrow: it checks that the Motion Brush payload remains
image/matte-clip-only and is suppressed in Retake Mode.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
CUSTOM_NODES = ROOT.parent
APP_ROOT = CUSTOM_NODES.parent

sys.path.insert(0, str(APP_ROOT))

# Pin ComfyUI's package named "utils" before importing any custom-node package.
import utils.install_util  # noqa: F401,E402
from server import PromptServer  # noqa: E402


class _NoopRoutes:
    def get(self, *args, **kwargs):
        return lambda fn: fn

    def post(self, *args, **kwargs):
        return lambda fn: fn


if not hasattr(PromptServer, "instance"):
    PromptServer.instance = type("_NoopPromptServer", (), {"routes": _NoopRoutes()})()

sys.path.insert(1, str(CUSTOM_NODES))

from LTX_Director_v2_motion_brush import ltx_director_guide as director_guide  # noqa: E402
from LTX_Director_v2_motion_brush import ltx_director_motion_brush_guides_v2 as motion_guides  # noqa: E402
from LTX_Director_v2_motion_brush import ltx_director_motion_brush_v2 as motion_brush  # noqa: E402


def build_payload(
    timeline: dict,
    motion: dict | None = None,
    start=0,
    duration=120,
    resize_method="maintain aspect ratio",
    resize_divisible_by=32,
) -> dict:
    raw = motion_brush._build_motion_tracks_payload(
        json.dumps(timeline),
        json.dumps(motion or {"version": 1, "segments": []}),
        start,
        duration,
        24,
        resize_method,
        resize_divisible_by,
    )
    return json.loads(raw)


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_close(actual: float, expected: float, label: str, tolerance: float = 1e-6) -> None:
    if abs(actual - expected) > tolerance:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_execute_fails_fast(timeline: dict, motion: dict) -> None:
    try:
        motion_brush.LTXDirectorMotionBrushV2.execute(
            None,
            None,
            0.0,
            5.0,
            5.0,
            0,
            120,
            120,
            json.dumps(timeline),
            json.dumps(motion),
            "",
            "",
            frame_rate=24,
    )
    except ValueError as exc:
        if "image and matte clips only" not in str(exc):
            raise
    else:
        raise AssertionError("execute should fail fast before model work when video segments and motion tracks are mixed")


def main() -> None:
    image_track = [[{"x": 0.1, "y": 0.2}, {"x": 0.8, "y": 0.7}]]
    legacy_track = [[{"x": 0.2, "y": 0.2}, {"x": 0.6, "y": 0.6}]]
    matte_track = [[{"x": 0.15, "y": 0.75}, {"x": 0.85, "y": 0.25}]]
    video_track = [[{"x": 0.3, "y": 0.4}, {"x": 0.4, "y": 0.5}]]

    mixed_timeline = {
        "retakeMode": False,
        "segments": [
            {
                "id": "img1",
                "type": "image",
                "start": 0,
                "length": 60,
                "imageFile": "whatdreamscost/a.png",
                "motionTracks": image_track,
                "motionCarryFrames": 24,
            },
            {
                "id": "legacy",
                "start": 20,
                "length": 20,
                "imageFile": "whatdreamscost/legacy.png",
                "motionTracks": legacy_track,
            },
            {
                "id": "vid1",
                "type": "video",
                "start": 60,
                "length": 60,
                "videoFile": "whatdreamscost/v.mp4",
                "motionTracks": video_track,
            },
            {
                "id": "matte1",
                "type": "matte",
                "start": 90,
                "length": 30,
                "matteColor": "#00ff00",
                "motionTracks": matte_track,
            },
            {
                "id": "txt1",
                "type": "text",
                "start": 30,
                "length": 30,
                "motionTracks": video_track,
            },
        ],
    }

    stale_motion = {
        "version": 1,
        "segments": [
            {
                "id": "vid1",
                "start": 60,
                "length": 60,
                "imageFile": "whatdreamscost/v.mp4",
                "tracks": video_track,
            },
            {
                "id": "img1",
                "start": 0,
                "length": 60,
                "imageFile": "whatdreamscost/a.png",
                "tracks": image_track,
            },
        ],
    }

    mixed_payload = build_payload(mixed_timeline, stale_motion)
    assert_equal([seg["id"] for seg in mixed_payload["segments"]], ["img1", "legacy", "matte1"], "mixed image/matte-only ids")
    img_payload = next(seg for seg in mixed_payload["segments"] if seg["id"] == "img1")
    assert_equal(img_payload["motionCarryFrames"], 24, "image payload preserves carry motion frames")
    matte_payload = next(seg for seg in mixed_payload["segments"] if seg["id"] == "matte1")
    assert_equal(matte_payload["type"], "matte", "matte payload type")
    assert_equal(matte_payload["matteColor"], "#00ff00", "matte payload color")

    brush_off_payload = build_payload({**mixed_timeline, "motionBrushMode": False}, stale_motion)
    assert_equal(brush_off_payload["segments"], [], "motion brush mode off suppresses payload")

    brush_on_payload = build_payload({**mixed_timeline, "motionBrushMode": True}, stale_motion)
    assert_equal([seg["id"] for seg in brush_on_payload["segments"]], ["img1", "legacy", "matte1"], "motion brush mode on preserves payload")

    untracked_next_timeline = {
        "retakeMode": False,
        "segments": [
            {
                "id": "tracked",
                "type": "image",
                "start": 0,
                "length": 60,
                "imageFile": "whatdreamscost/tracked.png",
                "motionTracks": image_track,
                "motionCarryFrames": 0,
            },
            {
                "id": "untracked",
                "type": "image",
                "start": 60,
                "length": 60,
                "imageFile": "whatdreamscost/untracked.png",
            },
        ],
    }
    untracked_next_payload = build_payload(untracked_next_timeline, start=0, duration=120)
    assert_equal([seg["id"] for seg in untracked_next_payload["segments"]], ["tracked"], "untracked next image is not emitted as a motion segment")
    assert_equal(untracked_next_payload["segments"][0]["nextStart"], 60, "tracked segment records untracked next image boundary")

    matte_only = {
        "retakeMode": False,
        "segments": [
            {
                "id": "matte1",
                "type": "matte",
                "start": 0,
                "length": 48,
                "matteColor": "#00ff00",
                "motionTracks": matte_track,
            }
        ],
    }
    matte_only_payload = build_payload(matte_only, start=0, duration=48)
    assert_equal([seg["id"] for seg in matte_only_payload["segments"]], ["matte1"], "matte-only payload ids")
    motion_brush._validate_motion_brush_timeline(matte_only, json.dumps(matte_only_payload))

    try:
        motion_brush._validate_motion_brush_timeline(mixed_timeline, json.dumps(mixed_payload))
    except ValueError as exc:
        if "image and matte clips only" not in str(exc):
            raise
    else:
        raise AssertionError("video plus motion tracks should fail fast")
    assert_execute_fails_fast(mixed_timeline, stale_motion)

    retake_timeline = {
        **mixed_timeline,
        "retakeMode": True,
        "retakeVideo": {"imageFile": "whatdreamscost/v.mp4"},
    }
    retake_payload = build_payload(retake_timeline, stale_motion)
    assert_equal(retake_payload["segments"], [], "retake suppresses motion brush")
    motion_brush._validate_motion_brush_timeline(retake_timeline, json.dumps(retake_payload))

    video_only = {
        "retakeMode": False,
        "segments": [
            {
                "id": "vid1",
                "type": "video",
                "start": 0,
                "length": 120,
                "videoFile": "whatdreamscost/v.mp4",
            }
        ],
    }
    video_only_payload = build_payload(video_only, stale_motion)
    assert_equal(video_only_payload["segments"], [], "video-only timeline ignores stale motion")
    motion_brush._validate_motion_brush_timeline(video_only, json.dumps(video_only_payload))

    clipped = build_payload(mixed_timeline, start=10, duration=30)
    clipped_by_id = {seg["id"]: seg for seg in clipped["segments"]}
    assert_equal(clipped_by_id["img1"]["start"], 0, "range clip img1 start")
    assert_equal(clipped_by_id["img1"]["length"], 30, "range clip img1 length")
    assert_equal(clipped_by_id["legacy"]["start"], 10, "range clip legacy start")
    assert_equal(clipped_by_id["legacy"]["length"], 20, "range clip legacy length")

    clipped_matte = build_payload(mixed_timeline, start=80, duration=30)
    clipped_matte_by_id = {seg["id"]: seg for seg in clipped_matte["segments"]}
    assert_equal(clipped_matte_by_id["matte1"]["start"], 10, "range clip matte start")
    assert_equal(clipped_matte_by_id["matte1"]["length"], 20, "range clip matte length")

    resized_payload = build_payload(mixed_timeline, start=0, duration=60, resize_method="pad", resize_divisible_by=16)
    resized_img = next(seg for seg in resized_payload["segments"] if seg["id"] == "img1")
    assert_equal(resized_img["resizeMethod"], "pad", "payload records resize method")
    assert_equal(resized_img["resizeDivisibleBy"], 16, "payload records resize divisibility")
    assert_equal(
        motion_brush._effective_resize_method_for_motion_brush("pad", json.dumps(resized_payload)),
        "maintain aspect ratio",
        "motion brush clamps unsafe resize methods",
    )
    assert_equal(
        motion_brush._effective_resize_method_for_motion_brush("crop", '{"version":1,"segments":[]}'),
        "crop",
        "non-brush timelines keep requested resize method",
    )

    pad_left = motion_guides._transform_motion_point_for_resize(
        {"x": 0.0, "y": 0.5},
        {"width": 100, "height": 100},
        "pad",
        200,
        100,
        1,
    )
    assert_close(pad_left["x"], 50 / 199, "pad remaps left edge into padded canvas")
    assert_close(pad_left["y"], 49.5 / 99, "pad preserves vertical midpoint")

    crop_top = motion_guides._transform_motion_point_for_resize(
        {"x": 0.5, "y": 0.0},
        {"width": 100, "height": 100},
        "crop",
        200,
        100,
        1,
    )
    assert_close(crop_top["x"], 99.5 / 199, "crop preserves horizontal midpoint")
    assert_close(crop_top["y"], 0.0, "crop clips cropped top edge")

    retake_mask = {"retakeStart": 24, "retakeLength": 48}
    assert_equal(
        director_guide._retake_latent_interval(retake_mask, 0, 16, 8, 121),
        (3, 9),
        "retake full-window interval",
    )
    assert_equal(
        director_guide._retake_latent_interval(retake_mask, 40, 16, 8, 121),
        (0, 4),
        "retake partial-overlap interval",
    )
    assert_equal(
        director_guide._retake_latent_interval(retake_mask, 80, 16, 8, 121),
        (0, 0),
        "retake no-overlap interval",
    )

    captured_source_preview = {}
    original_loader = motion_guides._load_motion_video_frames

    def fake_retake_loader(video_file, trim_start_frames, length_frames, director_fps, resample_mode="nearest"):
        captured_source_preview.update(
            {
                "video_file": video_file,
                "trim_start_frames": trim_start_frames,
                "length_frames": length_frames,
                "director_fps": director_fps,
                "resample_mode": resample_mode,
            }
        )
        return torch.full((int(length_frames), 2, 4, 3), 0.25, dtype=torch.float32)

    motion_guides._load_motion_video_frames = fake_retake_loader
    try:
        retake_preview = motion_guides.LTXDirectorMotionBrushV2RetakeSourcePreview.execute(
            {
                "timeline_data": json.dumps(
                    {
                        "retakeMode": True,
                        "retakeVideo": {"imageFile": "whatdreamscost/source.mp4"},
                    }
                ),
                "start_frame": 12,
                "duration_frames": 7,
                "frame_rate": 24,
                "resize_method": "maintain aspect ratio",
            },
            width=4,
            height=2,
            duration_frames=0,
            resize_method="match director guide",
            resample_mode="nearest",
            on_missing="error",
        )
    finally:
        motion_guides._load_motion_video_frames = original_loader

    preview_frames, preview_video, _, preview_summary_raw, preview_any_video = retake_preview.result
    assert_equal(list(preview_frames.shape), [8, 2, 4, 3], "retake source preview shape")
    assert_close(float(preview_frames.mean()), 0.25, "retake source preview pixels")
    preview_components = preview_video.get_components()
    preview_any_components = preview_any_video.get_components()
    assert_equal(list(preview_components.images.shape), [8, 2, 4, 3], "retake source preview video shape")
    assert_equal(list(preview_any_components.images.shape), [8, 2, 4, 3], "retake source preview wildcard video shape")
    assert_close(float(preview_components.frame_rate), 24.0, "retake source preview video fps")
    assert_equal(
        captured_source_preview,
        {
            "video_file": "whatdreamscost/source.mp4",
            "trim_start_frames": 12,
            "length_frames": 8,
            "director_fps": 24.0,
            "resample_mode": "nearest",
        },
        "retake source preview load request",
    )
    preview_summary = json.loads(preview_summary_raw)
    assert_equal(preview_summary["status"], "ok", "retake source preview status")
    assert_equal(preview_summary["resize_method"], "pad", "retake source preview maintain-ar fallback")

    missing_preview = motion_guides.LTXDirectorMotionBrushV2RetakeSourcePreview.execute(
        {"timeline_data": json.dumps({"retakeMode": False}), "duration_frames": 2},
        width=4,
        height=2,
        duration_frames=0,
        resize_method="match director guide",
        resample_mode="nearest",
        on_missing="blank frame",
    )
    missing_frames, missing_video, _, missing_summary_raw, missing_any_video = missing_preview.result
    assert_equal(list(missing_frames.shape), [3, 2, 4, 3], "missing retake source placeholder shape")
    assert_equal(list(missing_video.get_components().images.shape), [3, 2, 4, 3], "missing retake source placeholder video shape")
    assert_equal(list(missing_any_video.get_components().images.shape), [3, 2, 4, 3], "missing retake source placeholder wildcard video shape")
    assert_equal(json.loads(missing_summary_raw)["status"], "missing", "missing retake source placeholder status")

    matte = motion_brush._load_image_tensor({"type": "matte", "matteColor": "#0f0"}, 64, 32)
    assert_equal(list(matte.shape), [1, 32, 64, 3], "matte tensor shape")
    matte_rgb = [round(float(v), 4) for v in matte[0, 0, 0].tolist()]
    assert_equal(matte_rgb, [0.0, 1.0, 0.0], "matte tensor color")

    guide_timeline = {
        "segments": [
            {
                "id": "img1",
                "type": "image",
                "start": 0,
                "length": 24,
                "imageFile": "whatdreamscost/a.png",
                "guideStrength": 0.25,
            },
            {
                "id": "text1",
                "type": "text",
                "start": 24,
                "length": 24,
            },
            {
                "id": "empty_image",
                "type": "image",
                "start": 48,
                "length": 24,
            },
            {
                "id": "matte1",
                "type": "matte",
                "start": 72,
                "length": 24,
                "matteColor": "#00ff00",
                "guideStrength": 0.0,
            },
            {
                "id": "img2",
                "type": "image",
                "start": 96,
                "length": 24,
                "imageFile": "whatdreamscost/b.png",
            },
        ],
    }
    guide_segs = motion_brush._visual_guide_segments_from_timeline(guide_timeline, 0, 120)
    assert_equal([seg["id"] for seg in guide_segs], ["img1", "matte1", "img2"], "visual guide segment filter/order")
    fallback_strengths = motion_brush._parse_guide_strengths("0.90,0.80,0.70")
    resolved_strengths = [
        motion_brush._segment_guide_strength(seg, idx, fallback_strengths)
        for idx, seg in enumerate(guide_segs)
    ]
    assert_equal(resolved_strengths, [0.25, 0.0, 0.7], "per-segment guide strength overrides positional fallback")
    assert_equal(
        motion_brush._segment_guide_strength({"id": "matte_old", "type": "matte"}, 3, fallback_strengths),
        0.0,
        "matte guide strength default",
    )
    assert_equal(
        motion_guides._motion_segment_local_frame_count({"start": 0, "length": 120}, 120, 241),
        104,
        "adjacent motion guide segment leaves a blank temporal guard before the boundary",
    )
    assert_equal(
        motion_guides._motion_segment_frame_counts({"start": 0, "length": 120}, 120, 241),
        (120, 104),
        "adjacent motion guide samples full segment but renders only guarded frames",
    )
    assert_equal(
        motion_guides._motion_segment_frame_counts({"start": 0, "length": 120, "motionCarryFrames": 16}, 120, 241),
        (120, 120),
        "carry motion 16 reaches the next segment boundary",
    )
    assert_equal(
        motion_guides._motion_segment_frame_counts({"start": 0, "length": 120, "motionCarryFrames": 24}, 120, 241),
        (128, 128),
        "carry motion above 16 intentionally renders into the next segment",
    )
    assert_equal(
        motion_guides._motion_segment_local_frame_count({"start": 120, "length": 120}, None, 241),
        121,
        "final motion guide segment keeps terminal endpoint frame",
    )
    boundary_payload = json.dumps(
        {
            "version": 1,
            "duration_frames": 240,
            "segments": [
                {"id": "a", "start": 0, "length": 120, "tracks": [[{"x": 0.0, "y": 0.0}]]},
                {"id": "b", "start": 120, "length": 120, "tracks": [[{"x": 1.0, "y": 1.0}]]},
            ],
        }
    )
    boundary_out = motion_guides.LTXDirectorMotionBrushV2Guide.execute(
        boundary_payload,
        width=32,
        height=16,
        duration_frames=240,
        trail_frames=0,
        min_radius=1,
        max_radius=1,
    )
    boundary_frames = boundary_out.result[0]
    boundary_video = boundary_out.result[3]
    boundary_any_video = boundary_out.result[4]
    assert_equal(
        list(boundary_video.get_components().images.shape),
        [241, 16, 32, 3],
        "motion guide video output shape",
    )
    assert_equal(
        list(boundary_any_video.get_components().images.shape),
        [241, 16, 32, 3],
        "motion guide wildcard video output shape",
    )
    assert_close(float(boundary_frames[103, :3, :3, :].sum()), 3.0, "first motion guide segment reaches its last rendered frame")
    assert_close(float(boundary_frames[104, :3, :3, :].sum()), 0.0, "first motion guide segment leaves a blank guard band")
    assert_close(float(boundary_frames[120, :3, :3, :].sum()), 0.0, "first motion guide segment does not bleed into next segment")
    if float(boundary_frames[120, -3:, -3:, :].sum()) <= 0.0:
        raise AssertionError("second motion guide segment should begin on its first frame")
    untracked_boundary_payload = json.dumps(
        {
            "version": 1,
            "duration_frames": 240,
            "segments": [
                {"id": "a", "start": 0, "length": 120, "nextStart": 120, "tracks": [[{"x": 0.0, "y": 0.0}]]},
            ],
        }
    )
    untracked_boundary_out = motion_guides.LTXDirectorMotionBrushV2Guide.execute(
        untracked_boundary_payload,
        width=32,
        height=16,
        duration_frames=240,
        trail_frames=0,
        min_radius=1,
        max_radius=1,
    )
    untracked_boundary_frames = untracked_boundary_out.result[0]
    assert_close(float(untracked_boundary_frames[103, :3, :3, :].sum()), 3.0, "tracked segment reaches guard edge before an untracked image")
    assert_close(float(untracked_boundary_frames[104, :3, :3, :].sum()), 0.0, "carry 0 leaves a blank guard before an untracked image")
    assert_close(float(untracked_boundary_frames[120, :3, :3, :].sum()), 0.0, "carry 0 does not bleed into an untracked next image")
    untracked_carry_payload = json.dumps(
        {
            "version": 1,
            "duration_frames": 240,
            "segments": [
                {"id": "a", "start": 0, "length": 120, "nextStart": 120, "motionCarryFrames": 24, "tracks": [[{"x": 0.0, "y": 0.0}]]},
            ],
        }
    )
    untracked_carry_out = motion_guides.LTXDirectorMotionBrushV2Guide.execute(
        untracked_carry_payload,
        width=32,
        height=16,
        duration_frames=240,
        trail_frames=0,
        min_radius=1,
        max_radius=1,
    )
    untracked_carry_frames = untracked_carry_out.result[0]
    if float(untracked_carry_frames[127, :3, :3, :].sum()) <= 0.0:
        raise AssertionError("carry motion should intentionally render into an untracked next image")
    assert_close(float(untracked_carry_frames[128, :3, :3, :].sum()), 0.0, "untracked carry motion clamps to the configured carry window")
    carry_payload = json.dumps(
        {
            "version": 1,
            "duration_frames": 240,
            "segments": [
                {"id": "a", "start": 0, "length": 120, "motionCarryFrames": 24, "tracks": [[{"x": 0.0, "y": 0.0}]]},
                {"id": "b", "start": 120, "length": 120, "tracks": [[{"x": 1.0, "y": 1.0}]]},
            ],
        }
    )
    carry_out = motion_guides.LTXDirectorMotionBrushV2Guide.execute(
        carry_payload,
        width=32,
        height=16,
        duration_frames=240,
        trail_frames=0,
        min_radius=1,
        max_radius=1,
    )
    carry_frames = carry_out.result[0]
    if float(carry_frames[127, :3, :3, :].sum()) <= 0.0:
        raise AssertionError("carry motion should render the first segment into the next segment")
    assert_close(float(carry_frames[128, :3, :3, :].sum()), 0.0, "carry motion clamps to the configured carry window")
    assert_equal(
        motion_brush._segment_guide_insert_frames({"type": "image", "start": 120, "length": 120}, 0, 360),
        [120],
        "normal image guide emits one start keyframe",
    )
    assert_equal(
        motion_brush._segment_guide_insert_frames({"type": "image", "start": 120, "length": 120, "holdImage": True}, 0, 360),
        [120],
        "retired holdImage flag no longer adds extra guide keyframes",
    )
    assert_equal(
        motion_brush._segment_guide_insert_frames({"type": "image", "start": 120, "length": 120, "holdImage": True, "isEndFrame": True}, 0, 360),
        [239],
        "end-frame image guide preserves legacy end-frame behavior",
    )

    print("Phase 3 motion payload guardrails passed")


if __name__ == "__main__":
    main()
