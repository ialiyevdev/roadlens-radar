from pathlib import Path

import numpy as np
import pytest

from roadlens.detector import RoadLensDetector, letterbox


def test_letterbox_matches_zoo_rgb_no_normalization():
    image = np.full((100, 200, 3), [10, 20, 30], dtype=np.uint8)
    blob, scale = letterbox(image)
    assert scale == 3.2
    assert blob.shape == (1, 3, 640, 640)
    assert blob[0, :, 0, 0].tolist() == [30, 20, 10]
    assert blob[0, :, 639, 0].tolist() == [114, 114, 114]


def test_missing_weights_and_unsupported_export_are_actionable(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_model"):
        RoadLensDetector(tmp_path / "missing.onnx")
    with pytest.raises(ValueError, match="Supported"):
        RoadLensDetector(Path("unused"), input_size=512)


def test_decode_vehicle_class_filter_and_nms(monkeypatch, tmp_path):
    class Net:
        def setPreferableBackend(self, _): pass
        def setPreferableTarget(self, _): pass

    monkeypatch.setattr("cv2.dnn.readNetFromONNX", lambda _: Net())
    weights = tmp_path / "model.onnx"
    weights.touch()
    detector = RoadLensDetector(weights)
    output = np.zeros((1, 8400, 85), dtype=np.float32)
    for anchor, class_id in ((0, 2), (1, 2), (100, 0), (200, 7)):
        grid = detector.grids[anchor]
        output[0, anchor, :2] = np.array([100, 100]) / 8 - grid
        output[0, anchor, 2:4] = np.log(np.array([40, 30]) / 8)
        output[0, anchor, 4] = 0.9
        output[0, anchor, 5 + class_id] = 0.9
    detections = detector.decode(output, 1, 640, 640)
    assert sorted(d.category for d in detections) == ["car", "truck"]
    assert detections[0].bbox == pytest.approx((80, 85, 120, 115))
    assert detections[0].confidence == pytest.approx(0.81)


@pytest.mark.skipif(not Path("models/vehicle_detector.onnx").exists(), reason="Optional downloaded model not installed")
def test_real_model_cpu_inference_on_blank_frame():
    detector = RoadLensDetector(Path("models/vehicle_detector.onnx"))
    assert detector.detect(np.zeros((240, 320, 3), dtype=np.uint8)) == []


@pytest.mark.skipif(not Path("models/vehicle_detector.onnx").exists(), reason="Optional downloaded model not installed")
@pytest.mark.parametrize("input_size", [320, 416, 640])
def test_real_model_finds_vehicles_in_cc0_fixture(input_size):
    import cv2

    image = cv2.imread(str(Path(__file__).parent / "fixtures" / "city_traffic_cc0.jpg"))
    assert image is not None
    detections = RoadLensDetector(Path("models/vehicle_detector.onnx"), input_size=input_size).detect(image)
    assert any(detection.category == "car" for detection in detections)
    for detection in detections:
        x1, y1, x2, y2 = detection.bbox
        assert 0 <= x1 < x2 <= image.shape[1]
        assert 0 <= y1 < y2 <= image.shape[0]
        assert detection.confidence >= 0.35
