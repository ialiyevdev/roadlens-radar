"""Generate a video timing/control fixture; this is not real traffic footage."""

import argparse
from pathlib import Path

import cv2
import numpy as np


def make_video(path: Path, frames: int = 90, fps: int = 15) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (640, 360))
    if not writer.isOpened():
        raise RuntimeError("OpenCV could not create the MJPEG AVI timing fixture.")
    try:
        for index in range(frames):
            image = np.full((360, 640, 3), (29, 26, 23), dtype=np.uint8)
            cv2.putText(image, "SYNTHETIC TIMING FIXTURE", (30, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 200, 200), 1, cv2.LINE_AA)
            cv2.putText(image, "Not traffic footage or an accuracy benchmark", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 160, 160), 1, cv2.LINE_AA)
            cv2.putText(image, f"Frame {index + 1:03d} / {frames:03d}", (30, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (160, 210, 100), 1, cv2.LINE_AA)
            x = 30 + int(520 * index / max(1, frames - 1))
            cv2.rectangle(image, (x, 160), (x + 60, 200), (90, 140, 150), -1)
            writer.write(image)
    finally:
        writer.release()
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/synthetic-timing.avi"))
    parser.add_argument("--frames", type=int, default=90)
    args = parser.parse_args()
    if args.frames < 1:
        parser.error("--frames must be positive")
    print(make_video(args.output, args.frames))
