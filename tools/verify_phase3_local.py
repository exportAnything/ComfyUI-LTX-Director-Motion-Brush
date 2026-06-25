"""Run the local Phase 3 Motion Brush verification bundle.

This avoids model loading and generation. Use --base-url when a ComfyUI server
is already running and you also want live node/extension registration checked.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUSTOM_NODES = ROOT.parent
APP_ROOT = CUSTOM_NODES.parent

EXPECTED_NODES = {
    "LTXDirectorMotionBrushV2",
    "LTXDirectorMotionBrushV2Guide",
    "LTXDirectorMotionBrushV2RetakeSourcePreview",
    "LTXDirectorMotionBrushV2GuideAttention",
    "LTXDirectorMotionBrushV2SafeDownscaleFactor",
    "LTXDirectorMotionBrushV2DirectorGuide",
    "LTXDirectorMotionBrushV2CropGuides",
}

ROUTE_MARKERS = [
    "\"/exportanything_ltx_director_check_file\"",
    "\"/exportanything_ltx_director_get_audio\"",
    "\"/exportanything_ltx_director_open_folder\"",
    "\"/exportanything_ltx_director_upload_chunk\"",
]

FRONTEND_MARKERS = [
    "Motion Brush supports image and matte clips only",
    "Retake Mode (BETA)",
    "MIN_RETAKE_SECONDS",
    "Carry Motion",
    "selectedSegmentIds",
    "ltx-director-motion-brush-v2-styles",
]


def run(label: str, command: list[str], cwd: Path = ROOT) -> None:
    print(f"[phase3] {label}")
    subprocess.run(command, cwd=str(cwd), check=True)


def check_node_registration() -> None:
    print("[phase3] import node registration")
    sys.path.insert(0, str(APP_ROOT))
    import utils.install_util  # noqa: F401,PLC0415

    sys.path.insert(1, str(CUSTOM_NODES))
    import LTX_Director_v2_motion_brush as package  # noqa: PLC0415

    registered = set(package.NODE_CLASS_MAPPINGS)
    missing = sorted(EXPECTED_NODES - registered)
    if missing:
        raise AssertionError(f"Missing node registrations: {missing}")


def check_exportanything_routes() -> None:
    print("[phase3] exportAnything workspace/chunk routes")
    source = (ROOT / "ltx_director_motion_brush_v2.py").read_text(encoding="utf-8")
    missing = [marker for marker in ROUTE_MARKERS if marker not in source]
    if missing:
        raise AssertionError(f"Expected exportAnything route markers missing: {missing}")


def check_frontend_markers() -> None:
    print("[phase3] frontend source markers")
    source = (ROOT / "js_motion_brush_v2" / "ltx_director_motion_brush_v2.js").read_text(encoding="utf-8")
    missing = [marker for marker in FRONTEND_MARKERS if marker not in source]
    if missing:
        raise AssertionError(f"Expected frontend markers missing: {missing}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Optional running ComfyUI base URL for live node checks.")
    parser.add_argument("--skip-pip-check", action="store_true", help="Skip venv package consistency check.")
    args = parser.parse_args()

    run("motion payload guardrails", [sys.executable, str(ROOT / "tools" / "verify_phase3_motion_payload.py")])
    run(
        "python compile",
        [
            sys.executable,
            "-m",
            "py_compile",
            str(ROOT / "__init__.py"),
            str(ROOT / "ltx_director_motion_brush_v2.py"),
            str(ROOT / "ltx_director_motion_brush_guides_v2.py"),
            str(ROOT / "ltx_director_guide.py"),
            str(ROOT / "tools" / "verify_phase3_motion_payload.py"),
            str(ROOT / "tools" / "verify_phase3_live_nodes.py"),
            str(ROOT / "tools" / "verify_phase3_local.py"),
        ],
    )

    node = shutil.which("node")
    if not node:
        raise RuntimeError("node is required for the frontend syntax check")
    run("frontend syntax", [node, "--check", str(ROOT / "js_motion_brush_v2" / "ltx_director_motion_brush_v2.js")])

    if not args.skip_pip_check:
        run("pip check", [sys.executable, "-m", "pip", "check"], cwd=APP_ROOT)

    git = shutil.which("git")
    if git:
        run("git diff --check", [git, "diff", "--check"])

    check_node_registration()
    check_exportanything_routes()
    check_frontend_markers()

    if args.base_url:
        run(
            "live node registration",
            [sys.executable, str(ROOT / "tools" / "verify_phase3_live_nodes.py"), "--base-url", args.base_url],
        )

    print("[phase3] local verification passed")


if __name__ == "__main__":
    main()
