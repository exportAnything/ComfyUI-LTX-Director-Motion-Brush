from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KNOWN_GOOD = ROOT.parent.parent / "custom_nodes_disabled" / "WhatDreamsCost-ComfyUI_motion_brush_known_good"


MOTION_HELPERS = r'''

def _normalise_motion_point(point: dict, image_size: dict | None = None) -> dict[str, float] | None:
    try:
        x = float(point.get("x"))
        y = float(point.get("y"))
    except (AttributeError, TypeError, ValueError):
        return None
    if abs(x) <= 1.5 and abs(y) <= 1.5:
        return {
            "x": max(0.0, min(1.0, x)),
            "y": max(0.0, min(1.0, y)),
        }
    image_size = image_size or {}
    try:
        width = float(image_size.get("width") or image_size.get("w") or 1.0)
        height = float(image_size.get("height") or image_size.get("h") or 1.0)
    except (AttributeError, TypeError, ValueError):
        width, height = 1.0, 1.0
    return {
        "x": max(0.0, min(1.0, x / max(1.0, width))),
        "y": max(0.0, min(1.0, y / max(1.0, height))),
    }


def _normalise_motion_tracks(raw, image_size: dict | None = None) -> list[list[dict[str, float]]]:
    if not isinstance(raw, list):
        return []
    tracks = []
    for track in raw:
        if not isinstance(track, list):
            continue
        points = []
        for point in track:
            normalised = _normalise_motion_point(point, image_size)
            if normalised is not None:
                points.append({
                    "x": round(float(normalised["x"]), 6),
                    "y": round(float(normalised["y"]), 6),
                })
        if points:
            tracks.append(points)
    return tracks


def _motion_segment_keys(seg: dict) -> set[str]:
    keys = set()
    seg_id = seg.get("id")
    if seg_id:
        keys.add(f"id:{seg_id}")
    keys.add(
        "pos:{start}:{length}:{image}".format(
            start=int(round(float(seg.get("start", 0) or 0))),
            length=int(round(float(seg.get("length", 0) or 0))),
            image=seg.get("imageFile", "") or "",
        )
    )
    return keys


def _extract_motion_segments_from_timeline(timeline: dict) -> list[dict]:
    out = []
    for seg in timeline.get("segments", []):
        if not isinstance(seg, dict) or seg.get("type", "image") == "text":
            continue
        image_size = seg.get("imageSize") if isinstance(seg.get("imageSize"), dict) else {}
        tracks = _normalise_motion_tracks(seg.get("motionTracks") or seg.get("motion_tracks") or [], image_size)
        if not tracks:
            continue
        out.append({
            "id": seg.get("id", ""),
            "start": int(round(float(seg.get("start", 0) or 0))),
            "length": int(round(float(seg.get("length", 0) or 0))),
            "prompt": seg.get("prompt", ""),
            "imageFile": seg.get("imageFile", "") or seg.get("videoFile", ""),
            "imageSize": image_size,
            "pointsToSample": int(round(float(seg.get("motionPointsToSample", 121) or 121))),
            "tracks": tracks,
        })
    return out


def _clip_motion_segment(seg: dict, start_frame: int, duration_frames: int) -> dict | None:
    try:
        seg_start = int(round(float(seg.get("start", 0) or 0)))
        length = int(round(float(seg.get("length", 0) or 0)))
    except (TypeError, ValueError):
        return None
    if length <= 0:
        return None
    end_frame = int(start_frame) + int(duration_frames)
    if seg_start >= end_frame or seg_start + length <= start_frame:
        return None
    offset = max(0, int(start_frame) - seg_start)
    new_start = max(0, seg_start - int(start_frame))
    clipped_len = min(length - offset, int(duration_frames) - new_start)
    if clipped_len <= 0:
        return None
    image_size = seg.get("imageSize") if isinstance(seg.get("imageSize"), dict) else {}
    tracks = _normalise_motion_tracks(seg.get("tracks") or [], image_size)
    if not tracks:
        return None
    return {
        "id": seg.get("id", ""),
        "start": int(new_start),
        "length": int(clipped_len),
        "prompt": seg.get("prompt", ""),
        "imageFile": seg.get("imageFile", "") or "",
        "imageSize": image_size,
        "pointsToSample": int(round(float(seg.get("pointsToSample", 121) or 121))),
        "tracks": tracks,
    }


def _build_motion_tracks_payload(
    timeline_data: str,
    motion_tracks_data: str,
    start_frame: int,
    duration_frames: int,
    frame_rate: float,
) -> str:
    """Return sparse per-segment motion tracks clipped to the current Director range."""
    try:
        timeline = json.loads(timeline_data) if timeline_data else {}
    except (json.JSONDecodeError, TypeError):
        timeline = {}

    merged = []
    seen = set()

    try:
        parsed = json.loads(motion_tracks_data) if motion_tracks_data else {}
        parsed_segments = parsed.get("segments", []) if isinstance(parsed, dict) else []
    except (json.JSONDecodeError, TypeError):
        parsed_segments = []

    for source_seg in [*parsed_segments, *_extract_motion_segments_from_timeline(timeline)]:
        if not isinstance(source_seg, dict):
            continue
        keys = _motion_segment_keys(source_seg)
        if not keys.isdisjoint(seen):
            continue
        clipped = _clip_motion_segment(source_seg, int(start_frame), int(duration_frames))
        if not clipped:
            continue
        merged.append(clipped)
        seen.update(keys)

    return json.dumps({
        "version": 1,
        "start_frame": int(start_frame),
        "duration_frames": int(duration_frames),
        "frame_rate": float(frame_rate),
        "segments": merged,
    })
'''


JS_HELPERS = r'''
function clamp01(v) { return clamp(Number(v) || 0, 0, 1); }

const MOTION_TRACK_COLORS = ["#ef4444", "#22c55e", "#3b82f6", "#f59e0b", "#a855f7", "#06b6d4", "#f97316", "#84cc16"];
const MOTION_BRUSH_MAX_WIDTH = 1024;
const MOTION_BRUSH_MAX_HEIGHT = 560;
const MOTION_BRUSH_POINT_RADIUS = 5;
const MOTION_BRUSH_HIT_RADIUS = 12;
const MOTION_HISTORY_LIMIT = 80;

function normalizeMotionTracks(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(track => Array.isArray(track))
    .map(track =>
      track
        .filter(point => point && Number.isFinite(Number(point.x)) && Number.isFinite(Number(point.y)))
        .map(point => ({
          x: Number(clamp01(point.x).toFixed(6)),
          y: Number(clamp01(point.y).toFixed(6)),
        }))
    );
}

function hasMotionTrackPoints(raw) {
  return normalizeMotionTracks(raw).some(track => track.length > 0);
}

function cloneMotionTracks(raw) {
  return normalizeMotionTracks(raw).map(track => track.map(point => ({ ...point })));
}

function motionTracksEqual(a, b) {
  return JSON.stringify(cloneMotionTracks(a)) === JSON.stringify(cloneMotionTracks(b));
}

function ensureMotionSegment(seg) {
  if (!seg) return [];
  seg.motionTracks = normalizeMotionTracks(seg.motionTracks);
  if (seg.motionPointsToSample === undefined) seg.motionPointsToSample = 121;
  return seg.motionTracks;
}

function parseMotionPayload(jsonStr) {
  try {
    const parsed = jsonStr ? JSON.parse(jsonStr) : {};
    return parsed && Array.isArray(parsed.segments) ? parsed.segments : [];
  } catch (e) {
    return [];
  }
}

function motionSegmentPositionKey(seg) {
  if (!seg) return "";
  return [
    "pos",
    Math.round(seg.start || 0),
    Math.round(seg.length || 0),
    seg.imageFile || "",
  ].join(":");
}

function motionSegmentKey(seg) {
  if (!seg) return "";
  if (seg.id) return `id:${seg.id}`;
  return motionSegmentPositionKey(seg);
}
'''


MOTION_CSS = r'''
  .pr-motion-panel {
    display: flex;
    flex-direction: column;
    gap: 6px;
    border: 1px solid #111;
    border-radius: 6px;
    background: #181820;
    padding: 8px;
    box-sizing: border-box;
  }
  .pr-motion-panel.hidden {
    display: none;
  }
  .pr-motion-toolbar {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .pr-motion-toolbar .pr-btn {
    padding: 5px 9px;
    font-size: 10px;
  }
  .pr-motion-toolbar .pr-btn.active {
    background: #2f5d9f;
    border-color: #5d8bd0;
    color: #fff;
  }
  .pr-motion-toolbar .pr-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .pr-motion-status {
    margin-left: auto;
    color: #fbbf24;
    font-size: 11px;
    font-weight: 700;
    white-space: nowrap;
  }
  .pr-motion-canvas-wrap {
    width: 100%;
    min-height: 320px;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    overflow: auto;
    background: #0f1020;
    border-radius: 4px;
    border: 1px solid #111;
  }
  .pr-motion-canvas {
    display: block;
    outline: none;
    background: #11111c;
    touch-action: none;
  }
'''


MOTION_METHODS = r'''
  makeMotionButton(key, label, title, onClick) {
    const button = document.createElement("button");
    button.className = "pr-btn";
    button.type = "button";
    button.textContent = label;
    button.title = title;
    let handledPointerAt = 0;
    const run = (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!button.disabled) onClick();
    };
    button.addEventListener("pointerdown", (e) => {
      handledPointerAt = e.timeStamp || performance.now();
      run(e);
    });
    button.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const now = e.timeStamp || performance.now();
      if (now - handledPointerAt < 250) return;
      if (!button.disabled) onClick();
    });
    this.motionButtons[key] = button;
    return button;
  }

  createMotionBrushPanel() {
    this.motionButtons = {};
    this.motionPanel = document.createElement("div");
    this.motionPanel.className = "pr-motion-panel hidden";

    const toolbar = document.createElement("div");
    toolbar.className = "pr-motion-toolbar";
    toolbar.appendChild(this.makeMotionButton("select", "Select", "Move existing motion points", () => this.setMotionMode("select")));
    toolbar.appendChild(this.makeMotionButton("draw", "Draw", "Append motion points to the active track", () => this.setMotionMode("draw")));
    toolbar.appendChild(this.makeMotionButton("new", "+ Track", "Create a new empty motion track", () => this.createMotionTrack()));
    toolbar.appendChild(this.makeMotionButton("delete", "Delete", "Delete the active motion track", () => this.deleteMotionTrack()));
    toolbar.appendChild(this.makeMotionButton("undo", "Undo", "Undo the last motion-track edit on this segment", () => this.undoMotion()));
    toolbar.appendChild(this.makeMotionButton("redo", "Redo", "Redo the last undone motion-track edit on this segment", () => this.redoMotion()));
    toolbar.appendChild(this.makeMotionButton("clear", "Clear", "Clear all motion tracks on this keyframe", () => this.clearMotionTracks()));

    this.motionStatus = document.createElement("span");
    this.motionStatus.className = "pr-motion-status";
    toolbar.appendChild(this.motionStatus);

    const canvasWrap = document.createElement("div");
    canvasWrap.className = "pr-motion-canvas-wrap";

    this.motionCanvas = document.createElement("canvas");
    this.motionCanvas.className = "pr-motion-canvas";
    this.motionCanvas.tabIndex = 0;
    this.motionCtx = this.motionCanvas.getContext("2d");
    this.motionCanvas.addEventListener("pointerdown", (e) => this.onMotionPointerDown(e));
    this.motionCanvas.addEventListener("mousedown", (e) => this.onMotionPointerDown(e));
    this.motionCanvas.addEventListener("pointermove", (e) => this.onMotionPointerMove(e));
    this.motionCanvas.addEventListener("mousemove", (e) => this.onMotionPointerMove(e));
    this.motionCanvas.addEventListener("pointerup", (e) => this.onMotionPointerUp(e));
    this.motionCanvas.addEventListener("mouseup", (e) => this.onMotionPointerUp(e));
    this.motionCanvas.addEventListener("pointercancel", (e) => this.onMotionPointerUp(e));
    this.motionCanvas.addEventListener("lostpointercapture", () => {
      this.motionDrag = null;
      this.motionCanvas.style.cursor = this.motionMode === "draw" ? "crosshair" : "default";
    });

    canvasWrap.appendChild(this.motionCanvas);
    this.motionPanel.appendChild(toolbar);
    this.motionPanel.appendChild(canvasWrap);
  }

  hydrateMotionTracksFromWidget() {
    if (!this.motionTracksWidget || !this.timeline || !Array.isArray(this.timeline.segments)) return;
    const savedMotionByKey = new Map();
    for (const motionSeg of parseMotionPayload(this.motionTracksWidget.value)) {
      if (!motionSeg || !Array.isArray(motionSeg.tracks)) continue;
      savedMotionByKey.set(motionSegmentKey(motionSeg), motionSeg);
      savedMotionByKey.set(motionSegmentPositionKey(motionSeg), motionSeg);
    }
    for (const seg of this.timeline.segments) {
      if (!seg || seg.type === "text") continue;
      const savedMotion = savedMotionByKey.get(motionSegmentKey(seg)) || savedMotionByKey.get(motionSegmentPositionKey(seg));
      if (savedMotion && !hasMotionTrackPoints(seg.motionTracks)) {
        seg.motionTracks = savedMotion.tracks;
        if (savedMotion.pointsToSample !== undefined) seg.motionPointsToSample = savedMotion.pointsToSample;
        if (!seg.imageSize && savedMotion.imageSize) seg.imageSize = savedMotion.imageSize;
      }
      ensureMotionSegment(seg);
    }
  }

  getSelectedMotionSegment() {
    if (this.selectionType !== "image" || this.selectedIndex < 0) return null;
    const seg = this.timeline.segments[this.selectedIndex];
    if (!seg || seg.type === "text" || (!seg.imageB64 && !seg.imageFile && !seg.imgObj && !seg.videoEl)) return null;
    ensureMotionSegment(seg);
    return seg;
  }

  getMotionTracks(seg = this.getSelectedMotionSegment()) {
    return ensureMotionSegment(seg);
  }

  getMotionHistoryKey(seg = this.getSelectedMotionSegment()) {
    if (!seg) return "";
    return seg.id ? `id:${seg.id}` : `index:${this.selectedIndex}`;
  }

  getMotionHistory(seg = this.getSelectedMotionSegment()) {
    const key = this.getMotionHistoryKey(seg);
    if (!key) return null;
    if (!this.motionHistory.has(key)) {
      this.motionHistory.set(key, { undo: [], redo: [] });
    }
    return this.motionHistory.get(key);
  }

  pushMotionHistory(seg = this.getSelectedMotionSegment()) {
    const history = this.getMotionHistory(seg);
    if (!history) return;
    const snapshot = cloneMotionTracks(seg.motionTracks);
    const last = history.undo[history.undo.length - 1];
    if (!last || !motionTracksEqual(last, snapshot)) {
      history.undo.push(snapshot);
      if (history.undo.length > MOTION_HISTORY_LIMIT) history.undo.shift();
    }
    history.redo = [];
  }

  canUndoMotion(seg = this.getSelectedMotionSegment()) {
    const history = this.getMotionHistory(seg);
    return !!history && history.undo.length > 0;
  }

  canRedoMotion(seg = this.getSelectedMotionSegment()) {
    const history = this.getMotionHistory(seg);
    return !!history && history.redo.length > 0;
  }

  restoreMotionTracks(seg, snapshot) {
    if (!seg) return;
    seg.motionTracks = cloneMotionTracks(snapshot);
    const tracks = this.getMotionTracks(seg);
    this.motionActiveTrack = tracks.length === 0 ? 0 : Math.max(0, Math.min(this.motionActiveTrack, tracks.length - 1));
    this.commitChanges();
    this.updateMotionBrushUI();
  }

  undoMotion() {
    const seg = this.getSelectedMotionSegment();
    const history = this.getMotionHistory(seg);
    if (!seg || !history || history.undo.length === 0) return;
    history.redo.push(cloneMotionTracks(seg.motionTracks));
    this.restoreMotionTracks(seg, history.undo.pop());
  }

  redoMotion() {
    const seg = this.getSelectedMotionSegment();
    const history = this.getMotionHistory(seg);
    if (!seg || !history || history.redo.length === 0) return;
    history.undo.push(cloneMotionTracks(seg.motionTracks));
    this.restoreMotionTracks(seg, history.redo.pop());
  }

  syncMotionTracksData() {
    if (!this.motionTracksWidget) return;
    const segments = (this.timeline.segments || [])
      .filter((seg) => seg && seg.type !== "text" && Array.isArray(seg.motionTracks) && seg.motionTracks.some((track) => track.length > 0))
      .map((seg) => ({
        id: seg.id || "",
        start: Math.round(seg.start || 0),
        length: Math.round(seg.length || 0),
        prompt: seg.prompt || "",
        imageFile: seg.imageFile || "",
        imageSize: seg.imageSize || {},
        pointsToSample: seg.motionPointsToSample || 121,
        tracks: normalizeMotionTracks(seg.motionTracks),
      }));
    const payload = JSON.stringify({
      version: 1,
      duration_frames: this.getDurationFrames(),
      frame_rate: this.getFrameRate(),
      segments,
    });
    const oldValue = this.motionTracksWidget.value;
    this.motionTracksWidget.value = payload;
    if (this.node?.properties) this.node.properties.motion_tracks_data = payload;
    if (this.node?.onWidgetChanged && oldValue !== payload) {
      this.node.onWidgetChanged("motion_tracks_data", payload, oldValue, this.motionTracksWidget);
    }
  }

  setMotionMode(mode) {
    this.motionMode = mode === "draw" ? "draw" : "select";
    if (this.motionCanvas) {
      this.motionCanvas.style.cursor = this.motionMode === "draw" ? "crosshair" : "default";
    }
    this.updateMotionBrushUI();
  }

  createMotionTrack() {
    const seg = this.getSelectedMotionSegment();
    if (!seg) return;
    this.pushMotionHistory(seg);
    const tracks = this.getMotionTracks(seg);
    tracks.push([]);
    this.motionActiveTrack = tracks.length - 1;
    this.motionMode = "draw";
    this.commitChanges();
    this.updateMotionBrushUI();
  }

  deleteMotionTrack() {
    const seg = this.getSelectedMotionSegment();
    if (!seg) return;
    const tracks = this.getMotionTracks(seg);
    if (tracks.length === 0) return;
    this.pushMotionHistory(seg);
    tracks.splice(this.motionActiveTrack, 1);
    this.motionActiveTrack = Math.max(0, Math.min(this.motionActiveTrack, tracks.length - 1));
    this.commitChanges();
    this.updateMotionBrushUI();
  }

  clearMotionTracks() {
    const seg = this.getSelectedMotionSegment();
    if (!seg) return;
    if (this.getMotionTracks(seg).every((track) => track.length === 0)) return;
    this.pushMotionHistory(seg);
    seg.motionTracks = [];
    this.motionActiveTrack = 0;
    this.commitChanges();
    this.updateMotionBrushUI();
  }

  getMotionCanvasSize(seg) {
    const img = seg?.imgObj;
    const video = seg?.videoEl;
    const imgW = Math.max(1, seg?.imageSize?.width || img?.naturalWidth || img?.width || video?.videoWidth || seg?.videoWidth || 1024);
    const imgH = Math.max(1, seg?.imageSize?.height || img?.naturalHeight || img?.height || video?.videoHeight || seg?.videoHeight || 576);
    const scale = Math.min(MOTION_BRUSH_MAX_WIDTH / imgW, MOTION_BRUSH_MAX_HEIGHT / imgH, 1);
    return {
      width: Math.max(1, Math.round(imgW * scale)),
      height: Math.max(1, Math.round(imgH * scale)),
    };
  }

  updateMotionBrushUI() {
    if (!this.motionPanel || !this.motionCanvas) return;
    const seg = this.getSelectedMotionSegment();
    const visible = !!seg && !this.retakeMode;
    this.motionPanel.classList.toggle("hidden", !visible);
    if (!visible) return;

    const tracks = this.getMotionTracks(seg);
    if (tracks.length === 0) this.motionActiveTrack = 0;
    else this.motionActiveTrack = Math.max(0, Math.min(this.motionActiveTrack, tracks.length - 1));

    const size = this.getMotionCanvasSize(seg);
    const dpr = window.devicePixelRatio || 1;
    this.motionCanvas.style.width = `${size.width}px`;
    this.motionCanvas.style.height = `${size.height}px`;
    this.motionCanvas.width = Math.round(size.width * dpr);
    this.motionCanvas.height = Math.round(size.height * dpr);
    this.motionCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.motionView = { x: 0, y: 0, w: size.width, h: size.height };

    this.motionButtons.select.classList.toggle("active", this.motionMode === "select");
    this.motionButtons.draw.classList.toggle("active", this.motionMode === "draw");
    this.motionButtons.delete.disabled = tracks.length === 0;
    this.motionButtons.undo.disabled = !this.canUndoMotion(seg);
    this.motionButtons.redo.disabled = !this.canRedoMotion(seg);
    this.motionButtons.clear.disabled = tracks.every((track) => track.length === 0);
    this.motionCanvas.style.cursor = this.motionMode === "draw" ? "crosshair" : "default";
    this.motionStatus.textContent = tracks.length ? `Motion Track ${this.motionActiveTrack + 1} / ${tracks.length}` : "No motion tracks";
    this.renderMotionBrush();
  }

  motionPointToCanvas(point) {
    return {
      x: clamp01(point.x) * this.motionView.w,
      y: clamp01(point.y) * this.motionView.h,
    };
  }

  motionCanvasToPoint(pos) {
    return {
      x: Number(clamp01(pos.x / Math.max(1, this.motionView.w)).toFixed(6)),
      y: Number(clamp01(pos.y / Math.max(1, this.motionView.h)).toFixed(6)),
    };
  }

  getMotionPointer(e) {
    const rect = this.motionCanvas.getBoundingClientRect();
    const styleW = parseFloat(this.motionCanvas.style.width) || rect.width || 1;
    const styleH = parseFloat(this.motionCanvas.style.height) || rect.height || 1;
    return {
      x: (e.clientX - rect.left) * (styleW / Math.max(1, rect.width)),
      y: (e.clientY - rect.top) * (styleH / Math.max(1, rect.height)),
    };
  }

  hitTestMotionPoint(pos) {
    const seg = this.getSelectedMotionSegment();
    const tracks = this.getMotionTracks(seg);
    let best = null;
    let bestDist = Infinity;
    for (let ti = 0; ti < tracks.length; ti++) {
      for (let pi = 0; pi < tracks[ti].length; pi++) {
        const cp = this.motionPointToCanvas(tracks[ti][pi]);
        const d = Math.hypot(cp.x - pos.x, cp.y - pos.y);
        if (d < bestDist && d <= MOTION_BRUSH_HIT_RADIUS) {
          bestDist = d;
          best = { ti, pi };
        }
      }
    }
    return best;
  }

  onMotionPointerDown(e) {
    const seg = this.getSelectedMotionSegment();
    if (!seg || e.button !== 0) return;
    const now = e.timeStamp || performance.now();
    if (e.type === "mousedown" && now - this._lastMotionPointerDownAt < 250) return;
    if (e.type === "pointerdown") this._lastMotionPointerDownAt = now;
    e.preventDefault();
    e.stopPropagation();
    this.motionCanvas.focus();
    if (e.pointerId !== undefined && this.motionCanvas.setPointerCapture) {
      try { this.motionCanvas.setPointerCapture(e.pointerId); } catch (err) { }
    }
    const pos = this.getMotionPointer(e);

    if (this.motionMode === "draw") {
      const tracks = this.getMotionTracks(seg);
      if (tracks.length === 0) tracks.push([]);
      this.motionActiveTrack = Math.max(0, Math.min(this.motionActiveTrack, tracks.length - 1));
      this.pushMotionHistory(seg);
      tracks[this.motionActiveTrack].push(this.motionCanvasToPoint(pos));
      this.commitChanges();
      this.updateMotionBrushUI();
      if (e.pointerId !== undefined && this.motionCanvas.releasePointerCapture) {
        try { this.motionCanvas.releasePointerCapture(e.pointerId); } catch (err) { }
      }
      return;
    }

    const hit = this.hitTestMotionPoint(pos);
    if (hit) {
      this.motionActiveTrack = hit.ti;
      this.motionDrag = { ...hit, pointerId: e.pointerId, historyPushed: false };
      this.motionCanvas.style.cursor = "grabbing";
      this.updateMotionBrushUI();
    } else if (e.pointerId !== undefined && this.motionCanvas.releasePointerCapture) {
      try { this.motionCanvas.releasePointerCapture(e.pointerId); } catch (err) { }
    }
  }

  onMotionPointerMove(e) {
    const seg = this.getSelectedMotionSegment();
    if (!seg) return;
    const pos = this.getMotionPointer(e);
    if (this.motionDrag) {
      e.preventDefault();
      e.stopPropagation();
      const tracks = this.getMotionTracks(seg);
      if (!this.motionDrag.historyPushed) {
        this.pushMotionHistory(seg);
        this.motionDrag.historyPushed = true;
      }
      tracks[this.motionDrag.ti][this.motionDrag.pi] = this.motionCanvasToPoint(pos);
      this.commitChanges();
      this.renderMotionBrush();
      return;
    }

    const hit = this.hitTestMotionPoint(pos);
    this.motionCanvas.style.cursor = hit ? "grab" : (this.motionMode === "draw" ? "crosshair" : "default");
  }

  onMotionPointerUp(e) {
    if (!this.motionDrag) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.pointerId !== undefined && this.motionCanvas.releasePointerCapture) {
      try { this.motionCanvas.releasePointerCapture(e.pointerId); } catch (err) { }
    }
    this.motionDrag = null;
    this.motionCanvas.style.cursor = this.motionMode === "draw" ? "crosshair" : "default";
    this.commitChanges();
    this.updateMotionBrushUI();
  }

  drawMotionArrowhead(ctx, from, to, color, active) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const len = Math.hypot(dx, dy);
    if (len < 1) return;
    const ux = dx / len;
    const uy = dy / len;
    const size = active ? 10 : 8;
    const width = size * 0.6;
    const base = { x: to.x - ux * size, y: to.y - uy * size };
    ctx.beginPath();
    ctx.moveTo(to.x, to.y);
    ctx.lineTo(base.x - uy * width, base.y + ux * width);
    ctx.lineTo(base.x + uy * width, base.y - ux * width);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
  }

  renderMotionBrush() {
    if (!this.motionCtx || !this.motionCanvas) return;
    const seg = this.getSelectedMotionSegment();
    const ctx = this.motionCtx;
    const w = this.motionView.w || parseFloat(this.motionCanvas.style.width) || 1;
    const h = this.motionView.h || parseFloat(this.motionCanvas.style.height) || 1;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#11111c";
    ctx.fillRect(0, 0, w, h);
    if (!seg) return;

    if (seg.videoEl && seg.videoEl.readyState >= 2 && seg.videoEl.videoWidth > 0) {
      ctx.globalAlpha = 0.86;
      try { ctx.drawImage(seg.videoEl, 0, 0, w, h); } catch (err) { }
      ctx.globalAlpha = 1;
    } else if (seg.imgObj && seg.imgObj.complete && seg.imgObj.naturalWidth > 0) {
      ctx.globalAlpha = 0.86;
      ctx.drawImage(seg.imgObj, 0, 0, w, h);
      ctx.globalAlpha = 1;
    }

    const tracks = this.getMotionTracks(seg);
    for (let ti = 0; ti < tracks.length; ti++) {
      const track = tracks[ti];
      const active = ti === this.motionActiveTrack;
      const color = MOTION_TRACK_COLORS[ti % MOTION_TRACK_COLORS.length];
      ctx.globalAlpha = active ? 1 : 0.45;
      if (track.length >= 2) {
        ctx.beginPath();
        const first = this.motionPointToCanvas(track[0]);
        ctx.moveTo(first.x, first.y);
        for (let pi = 1; pi < track.length; pi++) {
          const p = this.motionPointToCanvas(track[pi]);
          ctx.lineTo(p.x, p.y);
        }
        ctx.strokeStyle = color;
        ctx.lineWidth = active ? 3 : 2;
        ctx.stroke();
        const arrowIdx = Math.max(1, Math.round((track.length - 1) * 0.75));
        this.drawMotionArrowhead(ctx, this.motionPointToCanvas(track[arrowIdx - 1]), this.motionPointToCanvas(track[arrowIdx]), color, active);
      }

      for (let pi = 0; pi < track.length; pi++) {
        const p = this.motionPointToCanvas(track[pi]);
        ctx.globalAlpha = 1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, MOTION_BRUSH_POINT_RADIUS + (active ? 2 : 0), 0, Math.PI * 2);
        ctx.fillStyle = active ? "#fff" : "rgba(255,255,255,0.55)";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(p.x, p.y, MOTION_BRUSH_POINT_RADIUS, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
  }
'''


INIT_SOURCE = r'''from comfy_api.latest import ComfyExtension, io
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
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Missing marker: {label}")
    return text.replace(old, new, 1)


def clean_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def generate_backend() -> None:
    src = (ROOT / "ltx_director.py").read_text(encoding="utf-8")
    for route in (
        '@PromptServer.instance.routes.get("/ltx_director_check_file")',
        '@PromptServer.instance.routes.get("/ltx_director_get_audio")',
        '@PromptServer.instance.routes.get("/ltx_director_open_folder")',
        '@PromptServer.instance.routes.post("/ltx_director_upload_chunk")',
    ):
        src = src.replace(route, "# Route provided by installed upstream LTX Director v2 package\n#" + route)

    src = src.replace("class LTXDirector(io.ComfyNode):", MOTION_HELPERS + "\nclass LTXDirectorMotionBrushV2(io.ComfyNode):", 1)
    src = src.replace('node_id="LTXDirector"', 'node_id="LTXDirectorMotionBrushV2"', 1)
    src = src.replace('display_name="LTX Director"', 'display_name="LTX Director Motion Brush V2"', 1)
    src = src.replace(
        '"Same as Prompt Relay Encode, but local prompts and segment lengths are edited "\n'
        '                "visually as draggable blocks on a timeline. The duration_frames input only sets the "\n'
        '                "timeline scale (pixel space) — actual frame count is still read from the latent."',
        '"LTX Director v2 with the same storyboard timeline plus per-keyframe "\n'
        '                "motion-brush tracks for LTX 2.3 motion-track IC-LoRA workflows."',
        1,
    )
    src = replace_once(
        src,
        '''                io.String.Input(
                    "timeline_data", default="",
                    tooltip="JSON state of the timeline editor (auto-managed; do not edit by hand).",
                ),
''',
        '''                io.String.Input(
                    "timeline_data", default="",
                    tooltip="JSON state of the timeline editor (auto-managed; do not edit by hand).",
                ),
                io.String.Input(
                    "motion_tracks_data", default='{"version":1,"segments":[]}',
                    tooltip="JSON state of per-segment motion brush tracks managed by the editor.",
                ),
''',
        "motion_tracks_data input",
    )
    src = replace_once(
        src,
        '''                io.Audio.Output(display_name="combined_audio", tooltip="Combined timeline audio layout."),
''',
        '''                io.Audio.Output(display_name="combined_audio", tooltip="Combined timeline audio layout."),
                io.String.Output("motion_tracks"),
''',
        "motion_tracks output",
    )
    src = replace_once(
        src,
        "                timeline_data, local_prompts, segment_lengths, global_prompt=\"\", guide_strength=\"\", epsilon=1e-3,",
        "                timeline_data, motion_tracks_data, local_prompts, segment_lengths, global_prompt=\"\", guide_strength=\"\", epsilon=1e-3,",
        "execute signature",
    )
    src = replace_once(
        src,
        '''        is_retake_mode = tdata.get("retakeMode", False)
        is_retake_active = is_retake_mode and tdata.get("retakeVideo") is not None

''',
        '''        is_retake_mode = tdata.get("retakeMode", False)
        is_retake_active = is_retake_mode and tdata.get("retakeVideo") is not None

        motion_tracks_payload = _build_motion_tracks_payload(
            timeline_data, motion_tracks_data, start_frame, duration_frames, frame_rate
        )

''',
        "motion payload build",
    )
    src = replace_once(
        src,
        "        return io.NodeOutput(patched, conditioning, latent, audio_latent, guide_data, motion_guide_data, float(frame_rate), audio_out)",
        "        return io.NodeOutput(patched, conditioning, latent, audio_latent, guide_data, motion_guide_data, float(frame_rate), audio_out, motion_tracks_payload)",
        "node output return",
    )
    src = re.sub(
        r"NODE_CLASS_MAPPINGS = \{.*?\}\s*NODE_DISPLAY_NAME_MAPPINGS = \{.*?\}\s*$",
        '''NODE_CLASS_MAPPINGS = {
    "LTXDirectorMotionBrushV2": LTXDirectorMotionBrushV2,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LTXDirectorMotionBrushV2": "LTX Director Motion Brush V2",
}
''',
        src,
        flags=re.S,
    )
    if "LTXDirectorMotionBrushV2" not in src or "motion_tracks_payload" not in src:
        raise RuntimeError("backend generation failed")
    (ROOT / "ltx_director_motion_brush_v2.py").write_text(clean_text(src), encoding="utf-8", newline="\n")


def generate_guides() -> None:
    src = (KNOWN_GOOD / "ltx_director_motion_guides.py").read_text(encoding="utf-8")
    replacements = {
        "LTXDirectorMotionBrushClearGuideAttention": "LTXDirectorMotionBrushV2GuideAttention",
        "LTXDirectorMotionBrushSafeDownscaleFactor": "LTXDirectorMotionBrushV2SafeDownscaleFactor",
        "LTXDirectorMotionBrushGuide": "LTXDirectorMotionBrushV2Guide",
        "LTX Director Motion Brush Guide Attention Fix": "LTX Director Motion Brush V2 Guide Attention",
        "LTX Director Motion Brush Safe Downscale Factor": "LTX Director Motion Brush V2 Safe Downscale Factor",
        "LTX Director Motion Brush Guide": "LTX Director Motion Brush V2 Guide",
    }
    for old, new in replacements.items():
        src = src.replace(old, new)
    (ROOT / "ltx_director_motion_brush_guides_v2.py").write_text(clean_text(src), encoding="utf-8", newline="\n")


def generate_js() -> None:
    src = (ROOT / "js" / "ltx_director.js").read_text(encoding="utf-8")
    src = src.replace(
        'const HIDDEN_WIDGET_NAMES = ["timeline_data", "local_prompts", "segment_lengths", "guide_strength", "audio_data", "use_custom_audio", "inpaint_audio", "use_custom_motion", "override_audio"];',
        'const HIDDEN_WIDGET_NAMES = ["timeline_data", "motion_tracks_data", "local_prompts", "segment_lengths", "guide_strength", "audio_data", "use_custom_audio", "inpaint_audio", "use_custom_motion", "override_audio"];',
        1,
    )
    src = replace_once(src, "function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }\n", "function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }\n" + JS_HELPERS + "\n", "js helpers")
    src = replace_once(src, "`;\n\nlet styleEl = document.getElementById(\"prompt-relay-styles\");", MOTION_CSS + "\n`;\n\nlet styleEl = document.getElementById(\"ltx-director-motion-brush-v2-styles\");", "motion css")
    src = src.replace('styleEl.id = "prompt-relay-styles";', 'styleEl.id = "ltx-director-motion-brush-v2-styles";', 1)
    src = replace_once(
        src,
        '    this.timelineDataWidget = this.node.widgets.find(w => w.name === "timeline_data");\n',
        '    this.timelineDataWidget = this.node.widgets.find(w => w.name === "timeline_data");\n    this.motionTracksWidget = this.node.widgets.find(w => w.name === "motion_tracks_data");\n',
        "motion widget",
    )
    src = replace_once(
        src,
        "    this.timeline = parseInitial(this.timelineDataWidget?.value);\n",
        "    this.timeline = parseInitial(this.timelineDataWidget?.value);\n    this.hydrateMotionTracksFromWidget();\n",
        "hydrate after parse",
    )
    src = replace_once(
        src,
        '    console.log("[LTXDirector debug] Constructor: parsed timeline:", JSON.stringify(this.timeline));\n',
        '    console.log("[LTXDirector debug] Constructor: parsed timeline:", JSON.stringify(this.timeline));\n\n    this.motionMode = "select";\n    this.motionActiveTrack = 0;\n    this.motionDrag = null;\n    this._lastMotionPointerDownAt = 0;\n    this.motionView = { x: 0, y: 0, w: 1, h: 1 };\n    this.motionButtons = {};\n    this.motionHistory = new Map();\n',
        "motion state",
    )
    src = replace_once(
        src,
        "    this.wrapper.appendChild(propContainer);\n    this.wrapper.appendChild(this.globalPropContainer);\n\n    this.container.appendChild(this.wrapper);\n",
        "    this.wrapper.appendChild(propContainer);\n    this.wrapper.appendChild(this.globalPropContainer);\n    this.createMotionBrushPanel();\n    this.wrapper.appendChild(this.motionPanel);\n\n    this.container.appendChild(this.wrapper);\n",
        "motion panel append",
    )
    src = replace_once(src, "\n  syncWidgetsAndUI() {\n", "\n" + MOTION_METHODS + "\n  syncWidgetsAndUI() {\n", "motion methods")
    src = replace_once(
        src,
        "  updateUIFromSelection() {\n",
        "  updateUIFromSelection() {\n    setTimeout(() => { if (this.updateMotionBrushUI) this.updateMotionBrushUI(); }, 0);\n",
        "update hook",
    )
    src = replace_once(
        src,
        "    if (this.timelineDataWidget) {\n      updateWidgetValue(this.timelineDataWidget, jsonStr);\n    }\n",
        "    if (this.timelineDataWidget) {\n      updateWidgetValue(this.timelineDataWidget, jsonStr);\n    }\n    this.syncMotionTracksData();\n",
        "sync motion tracks",
    )
    src = src.replace('  ["timeline_data", "{}"],\n', '  ["timeline_data", "{}"],\n  ["motion_tracks_data", "{\\"version\\":1,\\"segments\\":[]}"],\n', 1)
    src = src.replace('name: "LTXDirector"', 'name: "LTXDirectorMotionBrushV2"', 1)
    src = src.replace('nodeData.name === "LTXDirector"', 'nodeData.name === "LTXDirectorMotionBrushV2"', 1)
    src = src.replace('"LTXDirector debug]', '"LTXDirectorMotionBrushV2 debug]')
    src = src.replace("[LTXDirector debug]", "[LTXDirectorMotionBrushV2 debug]")
    src = src.replace("timeline_ui", "timeline_motion_brush_v2_ui")
    src = src.replace('timeline_data: "{}",', 'timeline_data: "{}",\n          motion_tracks_data: "{\\"version\\":1,\\"segments\\":[]}",', 1)
    src = src.replace('timeline_data: "{}",\n            epsilon', 'timeline_data: "{}",\n            motion_tracks_data: "{\\"version\\":1,\\"segments\\":[]}",\n            epsilon', 1)
    src = src.replace(
        'const skipWidgets = ["timeline_data", "local_prompts", "segment_lengths", "guide_strength", "timeline_motion_brush_v2_ui", "global_prompt"];',
        'const skipWidgets = ["timeline_data", "motion_tracks_data", "local_prompts", "segment_lengths", "guide_strength", "timeline_motion_brush_v2_ui", "global_prompt"];',
        1,
    )
    src = src.replace('"timeline_data", "use_custom_audio"', '"timeline_data", "motion_tracks_data", "use_custom_audio"')
    src = src.replace('"timeline_data", "local_prompts"', '"timeline_data", "motion_tracks_data", "local_prompts"')
    src = replace_once(
        src,
        '''          if (len <= 19) {
            names = SCHEMA_19;
          } else if (len === 21) {
            names = SCHEMA_21_NO_INPAINT;
          } else if (len === 22) {
            if (typeof info.widgets_values[13] === "number") {
              names = SCHEMA_22_NO_INPAINT;
            } else {
              names = SCHEMA_22_WITH_INPAINT;
            }
          }

          if (this.widgets) {
''',
        '''          if (len <= 19) {
            names = SCHEMA_19;
          } else if (len === 21) {
            names = SCHEMA_21_NO_INPAINT;
          } else if (len === 22) {
            if (typeof info.widgets_values[13] === "number") {
              names = SCHEMA_22_NO_INPAINT;
            } else {
              names = SCHEMA_22_WITH_INPAINT;
            }
          }

          if (names.includes("motion_tracks_data") && len === names.length - 1) {
            names = names.filter(name => name !== "motion_tracks_data");
          }

          if (this.widgets) {
''',
        "legacy schema compatibility",
    )
    src = src.replace('const tl = parseInitial(this._timelineEditor.timelineDataWidget?.value);', 'const tl = parseInitial(this._timelineEditor.timelineDataWidget?.value);\n            this._timelineEditor.timeline = tl;\n            this._timelineEditor.hydrateMotionTracksFromWidget();', 1)
    src = src.replace("this._timelineEditor.timeline = tl;\n\n            // Sync editor states", "// Sync editor states", 1)
    src = replace_once(
        src,
        '            "timeline_data", "local_prompts", "segment_lengths", "guide_strength", "timeline_motion_brush_v2_ui", "global_prompt"',
        '            "timeline_data", "motion_tracks_data", "local_prompts", "segment_lengths", "guide_strength", "timeline_motion_brush_v2_ui", "global_prompt"',
        "workflow export skip widgets",
    ) if '            "timeline_data", "local_prompts", "segment_lengths", "guide_strength", "timeline_motion_brush_v2_ui", "global_prompt"' in src else src
    src = src.replace('console.error("[PromptRelay] timeline editor init failed:", err);', 'console.error("[LTXDirectorMotionBrushV2] timeline editor init failed:", err);', 1)

    out_dir = ROOT / "js_motion_brush_v2"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "ltx_director_motion_brush_v2.js"
    out.write_text(clean_text(src), encoding="utf-8", newline="\n")


def write_init() -> None:
    (ROOT / "__init__.py").write_text(clean_text(INIT_SOURCE), encoding="utf-8", newline="\n")


def main() -> None:
    if not KNOWN_GOOD.exists():
        raise RuntimeError(f"Known-good source missing: {KNOWN_GOOD}")
    generate_backend()
    generate_guides()
    generate_js()
    write_init()


if __name__ == "__main__":
    main()
