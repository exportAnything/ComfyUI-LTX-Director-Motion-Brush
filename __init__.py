from comfy_api.latest import ComfyExtension, io
from typing_extensions import override

from .ltx_director_motion_brush_v2 import LTXDirectorMotionBrushV2
from .ltx_director_motion_brush_guides_v2 import (
    LTXDirectorMotionBrushV2Guide,
    LTXDirectorMotionBrushV2GuideAttention,
    LTXDirectorMotionBrushV2SafeDownscaleFactor,
)
from .ltx_director_guide import (
    LTXDirectorGuide as LTXDirectorMotionBrushV2DirectorGuide,
    LTXDirectorCropGuides as LTXDirectorMotionBrushV2CropGuides,
)


class LTXDirectorMotionBrushV2Extension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            LTXDirectorMotionBrushV2,
            LTXDirectorMotionBrushV2Guide,
            LTXDirectorMotionBrushV2GuideAttention,
            LTXDirectorMotionBrushV2SafeDownscaleFactor,
            LTXDirectorMotionBrushV2DirectorGuide,
            LTXDirectorMotionBrushV2CropGuides,
        ]


async def comfy_entrypoint() -> LTXDirectorMotionBrushV2Extension:
    return LTXDirectorMotionBrushV2Extension()


NODE_CLASS_MAPPINGS = {
    "LTXDirectorMotionBrushV2": LTXDirectorMotionBrushV2,
    "LTXDirectorMotionBrushV2Guide": LTXDirectorMotionBrushV2Guide,
    "LTXDirectorMotionBrushV2GuideAttention": LTXDirectorMotionBrushV2GuideAttention,
    "LTXDirectorMotionBrushV2SafeDownscaleFactor": LTXDirectorMotionBrushV2SafeDownscaleFactor,
    "LTXDirectorMotionBrushV2DirectorGuide": LTXDirectorMotionBrushV2DirectorGuide,
    "LTXDirectorMotionBrushV2CropGuides": LTXDirectorMotionBrushV2CropGuides,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LTXDirectorMotionBrushV2": "LTX Director Motion Brush V2",
    "LTXDirectorMotionBrushV2Guide": "LTX Director Motion Brush V2 Guide",
    "LTXDirectorMotionBrushV2GuideAttention": "LTX Director Motion Brush V2 Guide Attention",
    "LTXDirectorMotionBrushV2SafeDownscaleFactor": "LTX Director Motion Brush V2 Safe Downscale Factor",
    "LTXDirectorMotionBrushV2DirectorGuide": "LTX Director Motion Brush V2 Director Guide",
    "LTXDirectorMotionBrushV2CropGuides": "LTX Director Motion Brush V2 Crop Guides",
}

WEB_DIRECTORY = "./js_motion_brush_v2"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
