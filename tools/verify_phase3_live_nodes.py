"""Verify Phase 3 Motion Brush nodes against a running ComfyUI server."""

from __future__ import annotations

import argparse
import json
from urllib.error import URLError
from urllib.request import urlopen


EXPECTED_NODES = {
    "LTXDirectorMotionBrushV2": "LTX Director Motion Brush V2",
    "LTXDirectorMotionBrushV2Guide": "LTX Director Motion Brush V2 Guide",
    "LTXDirectorMotionBrushV2GuideAttention": "LTX Director Motion Brush V2 Guide Attention",
    "LTXDirectorMotionBrushV2SafeDownscaleFactor": "LTX Director Motion Brush V2 Safe Downscale Factor",
    "LTXDirectorMotionBrushV2DirectorGuide": "LTX Director Motion Brush V2 Director Guide",
    "LTXDirectorMotionBrushV2CropGuides": "LTX Director Motion Brush V2 Crop Guides",
}

EXPECTED_EXTENSION = "/extensions/LTX_Director_v2_motion_brush/ltx_director_motion_brush_v2.js"


def fetch_json(url: str):
    try:
        with urlopen(url, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8188", help="Running ComfyUI base URL.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    for class_name, display_name in EXPECTED_NODES.items():
        info = fetch_json(f"{base_url}/object_info/{class_name}")
        node_info = info.get(class_name) if isinstance(info, dict) else None
        if not isinstance(node_info, dict):
            raise AssertionError(f"{class_name} is missing from /object_info")
        actual_name = node_info.get("display_name")
        if actual_name != display_name:
            raise AssertionError(f"{class_name} display name: expected {display_name!r}, got {actual_name!r}")

    extensions = fetch_json(f"{base_url}/extensions")
    if EXPECTED_EXTENSION not in extensions:
        raise AssertionError(f"Missing frontend extension {EXPECTED_EXTENSION}")

    print("Phase 3 live Motion Brush node registration passed")


if __name__ == "__main__":
    main()
