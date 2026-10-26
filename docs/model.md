# Vehicle detector

RoadLens Phase 1 uses OpenCV Zoo's **YOLOX-S INT8 block-quantized COCO detector** with OpenCV DNN on the CPU. It runs locally after a one-time model download; PyTorch, an API key, and a GPU are not required. The underlying model recognizes COCO object categories, including people. RoadLens filters its output to cars, motorcycles, buses, and trucks, without vehicle make/model recognition or identity recognition.

From the project directory, run:

```powershell
python scripts/download_model.py
```

The standard-library downloader checks the exact byte count and SHA-256, writes a temporary `.part` file, and installs it atomically as `models/vehicle_detector.onnx`. A valid existing file is reused without a network request. A mismatched existing file is reported; remove it before downloading again. Downloaded weights are ignored by Git.

| Property | Pinned value |
| --- | --- |
| Upstream file | `object_detection_yolox_2022nov_int8bq.onnx` |
| Repository revision | `48b10fa505aeb51fbd127fc60a5c660040e823b7` |
| File size | 9,744,418 bytes (9.29 MiB) |
| SHA-256 | `dcaae0aaa2fea4167f89235ee340eb869d3707b25712218d4c7ce921ac90e2ba` |
| Declared ONNX input | `1 × 3 × 640 × 640`, float32, RGB |
| Verified OpenCV input sizes | Square 320, 416, and 640 pixels; configurable in RoadLens |
| Raw output at 640 | `1 × 8400 × 85` before grid decoding and NMS |
| Weight storage | INT8 blocks of 64; image input remains float32 |
| Runtime | OpenCV DNN, OpenCV backend, CPU target; verified with OpenCV 4.14.0 |

The [pinned upstream LFS metadata](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox/object_detection_yolox_2022nov_int8bq.onnx) records the artifact size and hash. The downloader fetches the [binary at that exact revision](https://media.githubusercontent.com/media/opencv/opencv_zoo/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox/object_detection_yolox_2022nov_int8bq.onnx), rather than Git's small LFS pointer file. OpenCV **4.14.0 is the minimum version verified by RoadLens** for this block-quantized artifact.

## Inference contract

Use the [OpenCV Zoo demo's](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox/demo.py) preprocessing conventions with the selected RoadLens input size `S`: convert OpenCV BGR frames to RGB, resize with the smaller of `S / height` and `S / width`, and place the resized frame at the top left of an `S × S` canvas filled with 114. Keep values in the 0–255 range. Transpose to contiguous float32 NCHW and add the batch dimension. Do not divide by 255 or subtract a mean.

The artifact's ONNX metadata declares a 640-square input. RoadLens independently verified that **OpenCV DNN 4.14.0 on CPU** accepts the same unmodified weights at **320, 416, and 640** and computes corresponding output shapes. It also verified changing between those sizes on the same network instance. This runtime-specific result establishes the three RoadLens options; compatibility with other sizes or other ONNX runtimes requires separate verification.

| Selected square size `S` | Input shape | Raw output shape | Grid locations at strides 8, 16, 32 |
| --- | --- | --- | --- |
| 320 | `1 × 3 × 320 × 320` | `1 × 2100 × 85` | `1600 + 400 + 100` |
| 416 | `1 × 3 × 416 × 416` | `1 × 3549 × 85` | `2704 + 676 + 169` |
| 640 | `1 × 3 × 640 × 640` | `1 × 8400 × 85` | `6400 + 1600 + 400` |

Follow the [upstream model wrapper's](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox/yolox.py) grid decoding with grids generated for the selected size: concatenate square grids of side `S / stride` for strides 8, 16, and 32. Decode centers as `(raw_xy + grid) * stride` and dimensions as `exp(raw_wh) * stride`. Multiply objectness by class probability, convert center/size boxes to corners, divide coordinates by the resize ratio, clip to the original frame, and apply non-maximum suppression. No additional sigmoid is needed for the output scores.

Vehicle class indices are zero-based COCO positions: **2 car, 3 motorcycle, 5 bus, and 7 truck**. COCO has no separate van category. Only these four classes are included in RoadLens vehicle results.

## Provenance and licensing

The [OpenCV Zoo model directory README](https://github.com/opencv/opencv_zoo/blob/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox/README.md#license) explicitly licenses all files in that directory under Apache-2.0, including this weight artifact. Its unmodified license is included at [`third_party/opencv_yolox_LICENSE.txt`](../third_party/opencv_yolox_LICENSE.txt); attribution is in [`third_party/NOTICE.md`](../third_party/NOTICE.md). The detector originates from [Megvii YOLOX](https://github.com/Megvii-BaseDetection/YOLOX), whose code is also Apache-2.0.

The smaller upstream YOLOX Nano weights were not selected because an [upstream request to clarify their separate pretrained-weight terms](https://github.com/Megvii-BaseDetection/YOLOX/issues/1865) remained unanswered when checked on 23 October 2026. OpenCV's explicit directory license applies to its own published artifacts; it does not establish terms for a different Nano download. [Ultralytics states](https://www.ultralytics.com/license) that its trained models use AGPL-3.0 by default, with an Enterprise option for proprietary deployment. RoadLens therefore uses the explicitly licensed OpenCV artifact.

This COCO-pretrained model has not been benchmarked on a representative RoadLens traffic dataset. No measured vehicle accuracy, real-time throughput, or calibration claim is made. Occlusion, small distant vehicles, lighting, and camera angle can affect detections. Weight quantization reduces download size; runtime speed and accuracy require evaluation on the target hardware and footage.

## Positive inference smoke check

On 23 October 2026, the real CPU detector processed [*City Traffic.jpg*](https://commons.wikimedia.org/wiki/File:City_Traffic.jpg) by Kanimozhi Vennila (16 October 2025), which the author dedicated to the public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). The unmodified [original JPEG](https://upload.wikimedia.org/wikipedia/commons/3/3c/City_Traffic.jpg), 720 × 1,280 pixels and 93,255 bytes, is included as the tracked fixture [`backend/tests/fixtures/city_traffic_cc0.jpg`](../backend/tests/fixtures/city_traffic_cc0.jpg), with [provenance and license details](../backend/tests/fixtures/README.md). Its SHA-256 is `9e18f000d1ab28d7415f719e48bdba0753188a42841be5a5f606d529a9fcfdc2`.

With OpenCV 4.14.0 on CPU and confidence threshold 0.35, the same image produced these illustrative smoke results:

| Input size | Car detections | Bus detections |
| --- | --- | --- |
| 320 × 320 | 3 | 0 |
| 416 × 416 | 5 | 1 |
| 640 × 640 | 8 | 1 |

All three raw outputs contained finite values, and repeating sizes after changing the network input reproduced these counts. This confirms that the actual weights, size-specific preprocessing, inference, and grid decoding run together. These are predictions from one image without ground-truth labels; they do not establish accuracy or general performance at any resolution. No camera was accessed.
