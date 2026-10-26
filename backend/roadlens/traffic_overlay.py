"""Optional traffic layers, separate from the existing speed-overlay contract."""

import cv2
import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict


class TrafficOverlaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    track_ids: bool = True
    vehicle_classes: bool = True
    traffic_lines: bool = True
    traffic_zones: bool = True
    direction_indicators: bool = False
    zone_occupancy: bool = True


def _label(image, text, position, color):
    anchor = (max(0, int(position[0])), max(15, int(position[1])))
    text = text.encode("ascii", "replace").decode()[:100]
    cv2.putText(image, text, anchor, cv2.FONT_HERSHEY_SIMPLEX, .45, (15, 20, 20), 3, cv2.LINE_AA)
    cv2.putText(image, text, anchor, cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1, cv2.LINE_AA)


def draw_traffic_regions(image, configuration, state, settings, transform=None):
    """Draw in the exact image space used by detector boxes and road calibration."""
    if not configuration:
        return
    configuration = configuration.model_dump() if hasattr(configuration, "model_dump") else configuration
    state = state or {}
    occupancy = state.get("zone_occupancy", {})
    for zone in configuration.get("zones", []):
        if not settings.traffic_zones and not settings.zone_occupancy:
            break
        points = zone["points"]
        if zone["coordinate_space"] == "ground":
            if transform is None or getattr(transform.data, "id", None) != configuration.get("calibration_id"):
                continue
            points = [transform.unproject(point) for point in points]
            if any(point is None for point in points):
                continue
        polygon = np.rint(points).astype(np.int32)
        color = (165, 165, 85)
        if settings.traffic_zones:
            layer = image.copy()
            cv2.fillPoly(layer, [polygon], color)
            cv2.addWeighted(layer, .12, image, .88, 0, dst=image)
            cv2.polylines(image, [polygon], True, color, 1, cv2.LINE_AA)
        if settings.zone_occupancy:
            value = occupancy.get(zone["id"], 0)
            count = value.get("count", 0) if isinstance(value, dict) else value
            _label(image, f"{zone['label']}: {count}", polygon[0], color)
    if settings.traffic_lines:
        for line in configuration.get("lines", []):
            start, end = np.asarray(line["start"]), np.asarray(line["end"])
            color = (130, 210, 205)
            cv2.line(image, tuple(np.rint(start).astype(int)), tuple(np.rint(end).astype(int)), color, 2, cv2.LINE_AA)
            _label(image, line["label"], start + (5, -8), color)
            if settings.direction_indicators:
                midpoint = (start + end) / 2
                delta = end - start
                normal = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
                cv2.arrowedLine(image, tuple(np.rint(midpoint).astype(int)),
                               tuple(np.rint(midpoint + normal * 24).astype(int)), color, 2, cv2.LINE_AA, tipLength=.3)


def traffic_overlay_routes(manager):
    router = APIRouter(prefix="/api/traffic")

    @router.get("/overlays")
    def get_overlays():
        return manager.traffic_overlays.model_dump()

    @router.put("/overlays")
    def set_overlays(settings: TrafficOverlaySettings):
        manager.set_traffic_overlays(settings)
        return settings

    return router
