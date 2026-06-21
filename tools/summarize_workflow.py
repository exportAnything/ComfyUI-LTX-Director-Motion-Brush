from __future__ import annotations

import json
import sys
from pathlib import Path


INTERESTING = {
    "LTXDirector",
    "LTXDirectorGuide",
    "LTXDirectorCropGuides",
    "LTXDirectorMotionBrush",
    "LTXDirectorMotionBrushGuide",
    "LTXDirectorMotionBrushClearGuideAttention",
    "LTXDirectorMotionBrushSafeDownscaleFactor",
    "LTXDirectorMotionBrushV2",
    "LTXDirectorMotionBrushV2Guide",
    "LTXDirectorMotionBrushV2GuideAttention",
    "LTXDirectorMotionBrushV2SafeDownscaleFactor",
    "LTXAddVideoICLoRAGuide",
    "SaveVideo",
    "VHS_VideoCombine",
}


def main() -> None:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", []) if isinstance(data, dict) else []
    print(f"{path}: nodes={len(nodes)}")
    for node in nodes:
        node_type = str(node.get("type", ""))
        if node_type in INTERESTING or "LTX" in node_type:
            outputs = [out.get("name") for out in node.get("outputs", [])]
            inputs = [inp.get("name") for inp in node.get("inputs", [])]
            print(node.get("id"), node_type, node.get("pos"), "OUT", outputs[:12], "IN", inputs[:12])


if __name__ == "__main__":
    main()
