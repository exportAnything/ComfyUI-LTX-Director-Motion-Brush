from comfy_api.latest import ComfyExtension, io
from typing_extensions import override

from .ltx_director_motion_brush_v2 import LTXDirectorMotionBrushV2
from .ltx_director_motion_brush_guides_v2 import (
    LTXDirectorMotionBrushV2Guide,
    LTXDirectorMotionBrushV2GuideAttention,
    LTXDirectorMotionBrushV2SafeDownscaleFactor,
)


class LTXDirectorMotionBrushV2Extension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            LTXDirectorMotionBrushV2,
            LTXDirectorMotionBrushV2Guide,
            LTXDirectorMotionBrushV2GuideAttention,
            LTXDirectorMotionBrushV2SafeDownscaleFactor,
        ]


async def comfy_entrypoint() -> LTXDirectorMotionBrushV2Extension:
    return LTXDirectorMotionBrushV2Extension()


NODE_CLASS_MAPPINGS = {
    "LTXDirectorMotionBrushV2": LTXDirectorMotionBrushV2,
    "LTXDirectorMotionBrushV2Guide": LTXDirectorMotionBrushV2Guide,
    "LTXDirectorMotionBrushV2GuideAttention": LTXDirectorMotionBrushV2GuideAttention,
    "LTXDirectorMotionBrushV2SafeDownscaleFactor": LTXDirectorMotionBrushV2SafeDownscaleFactor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LTXDirectorMotionBrushV2": "LTX Director Motion Brush V2",
    "LTXDirectorMotionBrushV2Guide": "LTX Director Motion Brush V2 Guide",
    "LTXDirectorMotionBrushV2GuideAttention": "LTX Director Motion Brush V2 Guide Attention",
    "LTXDirectorMotionBrushV2SafeDownscaleFactor": "LTX Director Motion Brush V2 Safe Downscale Factor",
}

WEB_DIRECTORY = "./js_motion_brush_v2"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
