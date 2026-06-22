"""Verify Phase 3 motion-brush payload guardrails.

This is intentionally narrow: it checks that the Motion Brush payload remains
image/matte-clip-only and is suppressed in Retake Mode.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


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
from LTX_Director_v2_motion_brush import ltx_director_motion_brush_v2 as motion_brush  # noqa: E402


def build_payload(timeline: dict, motion: dict | None = None, start=0, duration=120) -> dict:
    raw = motion_brush._build_motion_tracks_payload(
        json.dumps(timeline),
        json.dumps(motion or {"version": 1, "segments": []}),
        start,
        duration,
        24,
    )
    return json.loads(raw)


def assert_equal(actual, expected, label: str) -> None:
    if actual != expected:
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
    matte_payload = next(seg for seg in mixed_payload["segments"] if seg["id"] == "matte1")
    assert_equal(matte_payload["type"], "matte", "matte payload type")
    assert_equal(matte_payload["matteColor"], "#00ff00", "matte payload color")

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

    matte = motion_brush._load_image_tensor({"type": "matte", "matteColor": "#0f0"}, 64, 32)
    assert_equal(list(matte.shape), [1, 32, 64, 3], "matte tensor shape")
    matte_rgb = [round(float(v), 4) for v in matte[0, 0, 0].tolist()]
    assert_equal(matte_rgb, [0.0, 1.0, 0.0], "matte tensor color")

    print("Phase 3 motion payload guardrails passed")


if __name__ == "__main__":
    main()
