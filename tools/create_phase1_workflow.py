from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "example_workflows" / "LTX_Director_2_Workflow_Hotfix.json"
DST = ROOT / "example_workflows" / "LTX_Director_2_Motion_Brush_Phase1.json"


NOTE = """# LTX Director Motion Brush V2 Phase 1

This template keeps the official LTX Director v2 workflow intact and swaps only the main storyboard node for **LTX Director Motion Brush V2**.

Use the regular Director timeline as before. Select an image/keyframe segment, then draw motion tracks in the brush panel below the prompt area. The new `motion_tracks` output is appended after `combined_audio` so existing v2 connections stay in place.

Phase 1 intentionally keeps the stock v2 guide chain unchanged. To inject brush tracks into an IC-LoRA motion workflow, connect `motion_tracks` to **LTX Director Motion Brush V2 Guide**, then feed its `motion_guide` into the proven LTX 2.3 motion-track IC-LoRA chain."""


def next_id(nodes: list[dict]) -> int:
    return max(int(node.get("id", 0)) for node in nodes) + 1


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])

    director = next(node for node in nodes if node.get("type") == "LTXDirector")
    director["type"] = "LTXDirectorMotionBrushV2"
    director.setdefault("properties", {})["Node name for S&R"] = "LTXDirectorMotionBrushV2"
    director["properties"]["motion_brush_phase"] = "v2_phase1"
    director["title"] = "LTX Director Motion Brush V2"

    outputs = director.setdefault("outputs", [])
    if not any(out.get("name") == "motion_tracks" for out in outputs):
        outputs.append({
            "name": "motion_tracks",
            "type": "STRING",
            "links": None,
            "slot_index": len(outputs),
        })

    widgets = director.setdefault("widgets_values", [])
    if len(widgets) >= 7:
        widgets.insert(7, '{"version":1,"segments":[]}')

    note_id = next_id(nodes)
    x, y = director.get("pos", [7340, -930])
    note = {
        "id": note_id,
        "type": "Note",
        "pos": [x, y - 430],
        "size": [640, 300],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [],
        "outputs": [],
        "properties": {},
        "widgets_values": [NOTE],
        "color": "#232",
        "bgcolor": "#353",
    }
    nodes.append(note)

    data["nodes"] = nodes
    data["last_node_id"] = max(int(data.get("last_node_id", 0)), note_id)
    DST.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
