# Third-party model attribution

RoadLens uses the unmodified `object_detection_yolox_2022nov_int8bq.onnx` artifact from [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox), distributed under the Apache License, Version 2.0. The upstream directory explicitly applies that license to all its files. A copy is included in [opencv_yolox_LICENSE.txt](opencv_yolox_LICENSE.txt).

OpenCV's YOLOX model integration credits Sri Siddarth Chakaravarthy, Google Summer of Code 2022, OpenCV, for the project “Lightweight object detection models using OpenCV.”

The underlying YOLOX detector originates from [Megvii-BaseDetection/YOLOX](https://github.com/Megvii-BaseDetection/YOLOX), Copyright (c) 2021–2022 Megvii Inc. All rights reserved. YOLOX is described in *YOLOX: Exceeding YOLO Series in 2021* by Zheng Ge, Songtao Liu, Feng Wang, Zeming Li, and Jian Sun, [arXiv:2107.08430](https://arxiv.org/abs/2107.08430).

RoadLens's inference code follows the published model's input/output conventions. Model weights are downloaded separately and are not part of the source repository. Distributions containing those weights must retain the accompanying Apache-2.0 license and these attribution notices.

## Image fixture

`backend/tests/fixtures/city_traffic_cc0.jpg` is *City Traffic.jpg* by Kanimozhi Vennila, dedicated to the public domain under CC0 1.0. The [fixture provenance](../backend/tests/fixtures/README.md) retains the author's source declaration, original URL and checksum. CC0 does not require attribution; RoadLens retains it for provenance. The image is a still without independent ground-truth labels. Historical dashboard screenshots that display this image combine the MIT-licensed RoadLens interface with that CC0 image.
