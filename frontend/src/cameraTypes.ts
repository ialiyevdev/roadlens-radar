export interface CameraMetadata {
  camera: string;
  lens: string;
  zoom: string;
  focus: string;
  notes: string;
}

export interface CameraCalibrationInput {
  name: string;
  camera_configuration_id: string;
  checkerboard: { inner_columns: number; inner_rows: number; square_size_mm: number };
  metadata: CameraMetadata;
  rotation: 0 | 90 | 180 | 270;
  mirrored: boolean;
  crop: [number, number, number, number] | null;
}

export interface CameraIntrinsicProfile extends CameraCalibrationInput {
  id: string;
  width: number;
  height: number;
  model: "opencv_pinhole";
  camera_matrix: number[][];
  distortion_coefficients: number[];
  rms_reprojection_error_px: number;
  per_image_error_px: number[];
  used_image_count: number;
  rejected_image_count: number;
  images: {
    filename: string;
    sha256: string;
    accepted: boolean;
    reason: string;
    coverage: number | null;
    reprojection_error_px: number | null;
  }[];
  warnings: string[];
  pixel_coordinate_policy: "same_size_same_K_no_crop";
  provenance: "checkerboard_images" | "imported" | "synthetic";
}
