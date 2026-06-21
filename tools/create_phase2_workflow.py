from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "example_workflows" / "LTX_Director_2_Motion_Brush_Phase1.json"
DST = ROOT / "example_workflows" / "LTX_Director_2_Motion_Brush_Phase2_ICLoRA.json"

MOTION_LORA = "ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors"

NOTE = """# LTX Director Motion Brush V2 Phase 2

This workflow keeps the v2 Director storyboard/audio behavior, then injects the drawn motion-brush tracks into both sampler stages through the LTX 2.3 motion-track IC-LoRA chain.

Motion path:
`motion_tracks` -> `LTX Director Motion Brush V2 Guide` -> `LTXAddVideoICLoRAGuide` in each stage.

Model path:
Director model -> `LTXICLoRALoaderModelOnly` using `ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors` -> both DirectorGuide stages.

Safety path:
Each stage runs `LTX Director Motion Brush V2 Safe Downscale Factor` before `LTXAddVideoICLoRAGuide`, then `LTX Director Motion Brush V2 Guide Attention` before CFG/crop connections."""


def node_by_id(data: dict, node_id: int) -> dict:
    return next(node for node in data["nodes"] if int(node["id"]) == int(node_id))


def set_input(node: dict, name: str, link_id: int | None) -> None:
    for inp in node.get("inputs", []) or []:
        if inp.get("name") == name:
            inp["link"] = link_id
            return
    raise KeyError(f"Input {name!r} not found on node {node.get('id')} {node.get('type')}")


def set_output_links(node: dict, name: str, links: list[int] | None) -> None:
    for out in node.get("outputs", []) or []:
        if out.get("name") == name:
            out["links"] = links
            return
    raise KeyError(f"Output {name!r} not found on node {node.get('id')} {node.get('type')}")


def add_output_link(node: dict, name: str, link_id: int) -> None:
    for out in node.get("outputs", []) or []:
        if out.get("name") == name:
            links = out.get("links")
            if links is None:
                links = []
            if link_id not in links:
                links.append(link_id)
            out["links"] = links
            return
    raise KeyError(f"Output {name!r} not found on node {node.get('id')} {node.get('type')}")


def remove_links(data: dict, link_ids: set[int]) -> None:
    data["links"] = [link for link in data.get("links", []) if int(link[0]) not in link_ids]


def append_link(data: dict, link_id: int, src: int, src_slot: int, dst: int, dst_slot: int, link_type: str) -> None:
    data["links"].append([link_id, src, src_slot, dst, dst_slot, link_type])


def make_loader(node_id: int, pos: list[float]) -> dict:
    return {
        "id": node_id,
        "type": "LTXICLoRALoaderModelOnly",
        "pos": pos,
        "size": [570, 106],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [{"name": "model", "type": "MODEL", "link": 1093}],
        "outputs": [
            {"name": "model", "type": "MODEL", "links": [1094, 1095]},
            {"name": "latent_downscale_factor", "type": "FLOAT", "links": [1104, 1120]},
        ],
        "properties": {"cnr_id": "ComfyUI-LTXVideo", "Node name for S&R": "LTXICLoRALoaderModelOnly"},
        "widgets_values": [MOTION_LORA, 1],
    }


def make_brush_guide(node_id: int, pos: list[float]) -> dict:
    return {
        "id": node_id,
        "type": "LTXDirectorMotionBrushV2Guide",
        "pos": pos,
        "size": [360, 210],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"name": "optional_latent", "type": "LATENT", "link": 1128},
            {"name": "motion_tracks", "type": "STRING", "link": 1129},
        ],
        "outputs": [
            {"name": "motion_guide", "type": "IMAGE", "links": [1100, 1116, 1130]},
            {"name": "frame_idx", "type": "INT", "links": [1101, 1117]},
            {"name": "render_summary", "type": "STRING", "links": None},
        ],
        "properties": {"Node name for S&R": "LTXDirectorMotionBrushV2Guide"},
        "widgets_values": ['{"version":1,"duration_frames":120,"segments":[]}', 0, 0, 0, 50, 2, 8],
    }


def make_safe(node_id: int, pos: list[float], latent_link: int, requested_link: int, out_link: int) -> dict:
    return {
        "id": node_id,
        "type": "LTXDirectorMotionBrushV2SafeDownscaleFactor",
        "pos": pos,
        "size": [360, 120],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"name": "latent", "type": "LATENT", "link": latent_link},
            {"name": "requested_factor", "type": "FLOAT", "link": requested_link},
            {"name": "fallback_factor", "type": "FLOAT", "link": None},
        ],
        "outputs": [
            {"name": "latent_downscale_factor", "type": "FLOAT", "links": [out_link]},
            {"name": "summary", "type": "STRING", "links": None},
        ],
        "properties": {"Node name for S&R": "LTXDirectorMotionBrushV2SafeDownscaleFactor"},
        "widgets_values": [1.0],
    }


def make_add_guide(
    node_id: int,
    pos: list[float],
    positive_link: int,
    negative_link: int,
    vae_link: int,
    latent_link: int,
    image_link: int,
    frame_link: int,
    downscale_link: int,
    out_positive: int,
    out_negative: int,
    out_latent: int,
) -> dict:
    return {
        "id": node_id,
        "type": "LTXAddVideoICLoRAGuide",
        "pos": pos,
        "size": [316, 310],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"name": "positive", "type": "CONDITIONING", "link": positive_link},
            {"name": "negative", "type": "CONDITIONING", "link": negative_link},
            {"name": "vae", "type": "VAE", "link": vae_link},
            {"name": "latent", "type": "LATENT", "link": latent_link},
            {"name": "image", "type": "IMAGE", "link": image_link},
            {"name": "frame_idx", "type": "INT", "widget": {"name": "frame_idx"}, "link": frame_link},
            {
                "name": "latent_downscale_factor",
                "type": "FLOAT",
                "widget": {"name": "latent_downscale_factor"},
                "link": downscale_link,
            },
        ],
        "outputs": [
            {"name": "positive", "type": "CONDITIONING", "links": [out_positive]},
            {"name": "negative", "type": "CONDITIONING", "links": [out_negative]},
            {"name": "latent", "type": "LATENT", "links": [out_latent]},
        ],
        "properties": {"cnr_id": "ComfyUI-LTXVideo", "Node name for S&R": "LTXAddVideoICLoRAGuide"},
        "widgets_values": [0, 1.0, 1.0, "disabled", False, 256, 64],
    }


def make_attention(node_id: int, pos: list[float], pos_link: int, neg_link: int, out_pos: list[int], out_neg: list[int]) -> dict:
    return {
        "id": node_id,
        "type": "LTXDirectorMotionBrushV2GuideAttention",
        "pos": pos,
        "size": [360, 120],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"name": "positive", "type": "CONDITIONING", "link": pos_link},
            {"name": "negative", "type": "CONDITIONING", "link": neg_link},
        ],
        "outputs": [
            {"name": "positive", "type": "CONDITIONING", "links": out_pos},
            {"name": "negative", "type": "CONDITIONING", "links": out_neg},
        ],
        "properties": {"Node name for S&R": "LTXDirectorMotionBrushV2GuideAttention"},
        "widgets_values": [0.35],
    }


def make_create_video(node_id: int, pos: list[float]) -> dict:
    return {
        "id": node_id,
        "type": "CreateVideo",
        "pos": pos,
        "size": [270, 110],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [
            {"name": "images", "type": "IMAGE", "link": 1130},
            {"name": "audio", "type": "AUDIO", "link": None},
            {"name": "fps", "type": "FLOAT", "link": 1131},
        ],
        "outputs": [{"name": "VIDEO", "type": "VIDEO", "links": [1132]}],
        "properties": {"cnr_id": "comfy-core", "Node name for S&R": "CreateVideo"},
        "widgets_values": [24, 8],
    }


def make_save_video(node_id: int, pos: list[float]) -> dict:
    return {
        "id": node_id,
        "type": "SaveVideo",
        "pos": pos,
        "size": [320, 100],
        "flags": {},
        "order": 0,
        "mode": 0,
        "inputs": [{"name": "video", "type": "VIDEO", "link": 1132}],
        "outputs": [],
        "properties": {"cnr_id": "comfy-core", "Node name for S&R": "SaveVideo"},
        "widgets_values": ["video/LTX_Director_Motion_Brush_V2_Control", "auto", "auto"],
    }


def make_note(node_id: int, pos: list[float]) -> dict:
    return {
        "id": node_id,
        "type": "MarkdownNote",
        "pos": pos,
        "size": [720, 260],
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


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    nodes = data["nodes"]

    director = node_by_id(data, 131)
    guide1 = node_by_id(data, 132)
    guide2 = node_by_id(data, 133)
    cfg1 = node_by_id(data, 17)
    cfg2 = node_by_id(data, 28)
    crop1 = node_by_id(data, 54)
    crop2 = node_by_id(data, 55)
    concat1 = node_by_id(data, 18)
    concat2 = node_by_id(data, 29)
    vae_video = node_by_id(data, 36)

    remove_links(data, {1071, 1085, 1072, 1073, 1074, 1075, 1076, 1086, 1087, 1088, 1089, 1090})

    # Existing nodes now receive conditioning/latent/model through the Phase 2 injection chain.
    set_input(guide1, "model", 1094)
    set_input(guide2, "model", 1095)
    set_input(cfg1, "positive", 1107)
    set_input(cfg1, "negative", 1109)
    set_input(crop1, "positive", 1108)
    set_input(crop1, "negative", 1110)
    set_input(concat1, "video_latent", 1111)
    set_input(cfg2, "positive", 1123)
    set_input(cfg2, "negative", 1125)
    set_input(crop2, "positive", 1124)
    set_input(crop2, "negative", 1126)
    set_input(concat2, "video_latent", 1127)

    set_output_links(director, "model", [1093])
    add_output_link(director, "video_latent", 1128)
    add_output_link(director, "frame_rate", 1131)
    set_output_links(director, "motion_tracks", [1129])
    set_output_links(guide1, "positive", [1096])
    set_output_links(guide1, "negative", [1097])
    set_output_links(guide1, "latent", [1099, 1103])
    set_output_links(guide2, "positive", [1112])
    set_output_links(guide2, "negative", [1113])
    set_output_links(guide2, "latent", [1115, 1119])
    add_output_link(vae_video, "VAE", 1098)
    add_output_link(vae_video, "VAE", 1114)

    new_nodes = [
        make_brush_guide(135, [8120, -160]),
        make_loader(136, [8120, -430]),
        make_safe(137, [8580, -650], 1103, 1104, 1102),
        make_add_guide(138, [9000, -930], 1096, 1097, 1098, 1099, 1100, 1101, 1102, 1105, 1106, 1111),
        make_attention(139, [9360, -930], 1105, 1106, [1107, 1108], [1109, 1110]),
        make_safe(140, [8580, -100], 1119, 1120, 1118),
        make_add_guide(141, [9000, -380], 1112, 1113, 1114, 1115, 1116, 1117, 1118, 1121, 1122, 1127),
        make_attention(142, [9360, -380], 1121, 1122, [1123, 1124], [1125, 1126]),
        make_create_video(143, [8560, 190]),
        make_save_video(144, [8900, 190]),
        make_note(145, [7340, -1360]),
    ]
    nodes.extend(new_nodes)

    links_to_add = [
        (1093, 131, 0, 136, 0, "MODEL"),
        (1094, 136, 0, 132, 6, "MODEL"),
        (1095, 136, 0, 133, 6, "MODEL"),
        (1096, 132, 0, 138, 0, "CONDITIONING"),
        (1097, 132, 1, 138, 1, "CONDITIONING"),
        (1098, 36, 0, 138, 2, "VAE"),
        (1099, 132, 2, 138, 3, "LATENT"),
        (1100, 135, 0, 138, 4, "IMAGE"),
        (1101, 135, 1, 138, 5, "INT"),
        (1102, 137, 0, 138, 6, "FLOAT"),
        (1103, 132, 2, 137, 0, "LATENT"),
        (1104, 136, 1, 137, 1, "FLOAT"),
        (1105, 138, 0, 139, 0, "CONDITIONING"),
        (1106, 138, 1, 139, 1, "CONDITIONING"),
        (1107, 139, 0, 17, 1, "CONDITIONING"),
        (1108, 139, 0, 54, 0, "CONDITIONING"),
        (1109, 139, 1, 17, 2, "CONDITIONING"),
        (1110, 139, 1, 54, 1, "CONDITIONING"),
        (1111, 138, 2, 18, 0, "LATENT"),
        (1112, 133, 0, 141, 0, "CONDITIONING"),
        (1113, 133, 1, 141, 1, "CONDITIONING"),
        (1114, 36, 0, 141, 2, "VAE"),
        (1115, 133, 2, 141, 3, "LATENT"),
        (1116, 135, 0, 141, 4, "IMAGE"),
        (1117, 135, 1, 141, 5, "INT"),
        (1118, 140, 0, 141, 6, "FLOAT"),
        (1119, 133, 2, 140, 0, "LATENT"),
        (1120, 136, 1, 140, 1, "FLOAT"),
        (1121, 141, 0, 142, 0, "CONDITIONING"),
        (1122, 141, 1, 142, 1, "CONDITIONING"),
        (1123, 142, 0, 28, 1, "CONDITIONING"),
        (1124, 142, 0, 55, 0, "CONDITIONING"),
        (1125, 142, 1, 28, 2, "CONDITIONING"),
        (1126, 142, 1, 55, 1, "CONDITIONING"),
        (1127, 141, 2, 29, 0, "LATENT"),
        (1128, 131, 2, 135, 0, "LATENT"),
        (1129, 131, 8, 135, 1, "STRING"),
        (1130, 135, 0, 143, 0, "IMAGE"),
        (1131, 131, 6, 143, 2, "FLOAT"),
        (1132, 143, 0, 144, 0, "VIDEO"),
    ]
    for link in links_to_add:
        append_link(data, *link)

    data["last_node_id"] = 145
    data["last_link_id"] = 1132
    for order, node in enumerate(data["nodes"]):
        node["order"] = order

    DST.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
