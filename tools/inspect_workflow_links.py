from __future__ import annotations

import json
import sys
from pathlib import Path


INTERESTING = {
    "CFGGuider",
    "KSampler",
    "SamplerCustomAdvanced",
    "LTXAddVideoICLoRAGuide",
    "LTXDirector",
    "LTXDirectorCropGuides",
    "LTXDirectorGuide",
    "LTXDirectorMotionBrush",
    "LTXDirectorMotionBrushClearGuideAttention",
    "LTXDirectorMotionBrushGuide",
    "LTXDirectorMotionBrushSafeDownscaleFactor",
    "LTXDirectorMotionBrushV2",
    "LTXDirectorMotionBrushV2Guide",
    "LTXDirectorMotionBrushV2GuideAttention",
    "LTXDirectorMotionBrushV2SafeDownscaleFactor",
    "LTXICLoRALoaderModelOnly",
    "LTXVConcatAVLatent",
    "LTXVLatentUpsampler",
    "LTXVSeparateAVLatent",
    "SaveVideo",
}


def slot_name(node: dict, direction: str, slot: int) -> str:
    items = node.get(direction, []) or []
    if 0 <= slot < len(items):
        return str(items[slot].get("name", "?"))
    return "?"


def main() -> None:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = {int(node.get("id")): node for node in data.get("nodes", [])}

    print(f"{path}: nodes={len(nodes)} links={len(data.get('links', []) or [])}")
    for node in data.get("nodes", []):
        node_type = str(node.get("type", ""))
        if node_type not in INTERESTING and "LTX" not in node_type:
            continue
        print(f"NODE {node.get('id')} {node_type} pos={node.get('pos')}")
        for idx, inp in enumerate(node.get("inputs", []) or []):
            print(f"  IN {idx}: {inp.get('name')} type={inp.get('type')} link={inp.get('link')}")
        for idx, out in enumerate(node.get("outputs", []) or []):
            print(f"  OUT {idx}: {out.get('name')} type={out.get('type')} links={out.get('links')}")

    print("LINKS")
    for link in data.get("links", []) or []:
        link_id, src_id, src_slot, dst_id, dst_slot, *_ = link
        src = nodes.get(int(src_id), {})
        dst = nodes.get(int(dst_id), {})
        src_type = str(src.get("type", ""))
        dst_type = str(dst.get("type", ""))
        if src_type not in INTERESTING and dst_type not in INTERESTING and "LTX" not in src_type and "LTX" not in dst_type:
            continue
        print(
            f"{link_id}: {src_id}:{src_slot} {src_type}.{slot_name(src, 'outputs', int(src_slot))} "
            f"-> {dst_id}:{dst_slot} {dst_type}.{slot_name(dst, 'inputs', int(dst_slot))}"
        )


if __name__ == "__main__":
    main()
