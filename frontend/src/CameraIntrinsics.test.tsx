import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CameraIntrinsics from "./CameraIntrinsics";
import { cameraApi } from "./cameraApi";
import type { CameraIntrinsicProfile } from "./cameraTypes";
import { initialSession } from "./useSession";
import type { Session } from "./types";

vi.mock("./cameraApi", () => ({ cameraApi: {
  profiles: vi.fn(), calibrate: vi.fn(), importProfile: vi.fn(), remove: vi.fn(), activate: vi.fn(),
} }));

const profile: CameraIntrinsicProfile = {
  id: "cdb7f070-40b1-4f10-9b31-f85661a9c5dc", name: "Synthetic webcam model",
  camera_configuration_id: "synthetic-640x480", width: 640, height: 480,
  rotation: 0, mirrored: false, crop: null, model: "opencv_pinhole",
  metadata: { camera: "Synthetic", lens: "", zoom: "fixed", focus: "fixed", notes: "" },
  checkerboard: { inner_columns: 9, inner_rows: 6, square_size_mm: 25 },
  camera_matrix: [[600, 0, 320], [0, 610, 240], [0, 0, 1]],
  distortion_coefficients: [-.1, .01, 0, 0, 0], rms_reprojection_error_px: .125,
  per_image_error_px: [.125, .125, .125, .125, .125, .125], used_image_count: 6,
  rejected_image_count: 1, warnings: ["Synthetic calibration does not establish speed accuracy."],
  images: [{ filename: "synthetic.png", sha256: "a".repeat(64), accepted: true, reason: "Corners detected", coverage: .2, reprojection_error_px: .125 }],
  pixel_coordinate_policy: "same_size_same_K_no_crop", provenance: "synthetic",
};
const session: Session = { ...initialSession, width: 640, height: 480,
  geometry: { width: 640, height: 480, rotation: 0, mirrored: false, crop: null } };
const perform = vi.fn(async (operation: () => Promise<Session>) => { await operation(); });

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(cameraApi.profiles).mockResolvedValue({ profiles: [profile] });
  vi.mocked(cameraApi.activate).mockResolvedValue(session);
  vi.mocked(cameraApi.calibrate).mockResolvedValue(profile);
  vi.mocked(cameraApi.importProfile).mockResolvedValue(profile);
  vi.mocked(cameraApi.remove).mockResolvedValue({ deleted: true });
});

describe("optional camera calibration", () => {
  it("explains coordinate stages and remains optional in the empty state", async () => {
    vi.mocked(cameraApi.profiles).mockResolvedValue({ profiles: [] });
    render(<CameraIntrinsics session={initialSession} connected perform={perform} />);
    expect(await screen.findByText(/No camera intrinsic profiles saved/)).toBeInTheDocument();
    expect(screen.getByText("source image pixels")).toBeInTheDocument();
    expect(screen.getByText(/Independent reference events establish speed evidence/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fit and save camera profile' })).toBeDisabled();
  });

  it("requires explicit unchanged-configuration confirmation before applying", async () => {
    const user = userEvent.setup();
    render(<CameraIntrinsics session={session} connected perform={perform} />);
    await screen.findByRole('option', { name: /Synthetic webcam model/ });
    await user.selectOptions(screen.getByLabelText('Camera intrinsic profile'), profile.id);
    expect(screen.getByText('0.1250 px')).toBeInTheDocument();
    expect(screen.getByText('Synthetic target evidence')).toBeInTheDocument();
    const apply = screen.getByRole('button', { name: 'Apply lens correction' });
    expect(apply).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /I checked that camera/ }));
    await user.click(apply);
    await waitFor(() => expect(cameraApi.activate).toHaveBeenCalledWith(profile.id, true));
    expect(perform).toHaveBeenCalledOnce();
  });

  it("blocks resolution mismatch even after confirmation", async () => {
    render(<CameraIntrinsics session={{ ...session, width: 1280 }} connected perform={perform} />);
    await screen.findByRole('option', { name: /Synthetic webcam model/ });
    fireEvent.change(screen.getByLabelText('Camera intrinsic profile'), { target: { value: profile.id } });
    fireEvent.click(screen.getByRole('checkbox', { name: /I checked that camera/ }));
    expect(screen.getByRole('button', { name: 'Apply lens correction' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Profile resolution differs');
  });

  it("uploads target metadata and distinct images then selects the saved profile", async () => {
    render(<CameraIntrinsics session={session} connected perform={perform} />);
    fireEvent.change(screen.getByLabelText('Profile name'), { target: { value: 'New target fit' } });
    fireEvent.change(screen.getByLabelText('Camera configuration ID'), { target: { value: 'window-webcam' } });
    const files = Array.from({ length: 6 }, (_, i) => new File([`target${i}`], `target${i}.png`, { type: 'image/png' }));
    fireEvent.change(screen.getByLabelText('Checkerboard photos'), { target: { files } });
    fireEvent.click(screen.getByRole('button', { name: 'Fit and save camera profile' }));
    await waitFor(() => expect(cameraApi.calibrate).toHaveBeenCalledWith(expect.objectContaining({
      name: 'New target fit', camera_configuration_id: 'window-webcam',
      checkerboard: { inner_columns: 9, inner_rows: 6, square_size_mm: 25 },
    }), files));
    await waitFor(() => expect(screen.getByLabelText('Camera intrinsic profile')).toHaveValue(profile.id));
  });

  it("imports JSON and exposes profile exports and both pixel previews", async () => {
    render(<CameraIntrinsics session={session} connected perform={perform} />);
    const file = new File(['{}'], 'profile.json', { type: 'application/json' });
    Object.defineProperty(file, 'text', { value: async () => JSON.stringify(profile) });
    fireEvent.change(screen.getByLabelText('Import camera profile JSON'), { target: { files: [file] } });
    await waitFor(() => expect(cameraApi.importProfile).toHaveBeenCalledWith(profile));
    expect(await screen.findByRole('link', { name: 'Export camera JSON' })).toHaveAttribute('href', `/api/camera-profiles/${profile.id}/export`);
    fireEvent.click(screen.getByRole('button', { name: 'Preview original and corrected' }));
    expect(screen.getByAltText('Original frame in source pixel coordinates')).toHaveAttribute('src', expect.stringContaining('corrected=false'));
    expect(screen.getByAltText('Corrected frame in undistorted pixel coordinates')).toHaveAttribute('src', expect.stringContaining('corrected=true'));
    fireEvent.error(screen.getByAltText('Corrected frame in undistorted pixel coordinates'));
    expect(screen.getByRole('alert')).toHaveTextContent('Frame preview unavailable');
  });

  it("reports malformed imports and fitting errors without applying a model", async () => {
    render(<CameraIntrinsics session={session} connected perform={perform} />);
    const file = new File(['bad'], 'bad.json', { type: 'application/json' });
    Object.defineProperty(file, 'text', { value: async () => 'bad json' });
    fireEvent.change(screen.getByLabelText('Import camera profile JSON'), { target: { files: [file] } });
    expect(await screen.findByRole('alert')).toHaveTextContent('valid camera profile JSON');
    expect(cameraApi.importProfile).not.toHaveBeenCalled();
    expect(cameraApi.activate).not.toHaveBeenCalled();
  });

  it("deletes inactive profiles and resets the selection", async () => {
    render(<CameraIntrinsics session={session} connected perform={perform} />);
    await screen.findByRole('option', { name: /Synthetic webcam model/ });
    fireEvent.change(screen.getByLabelText('Camera intrinsic profile'), { target: { value: profile.id } });
    fireEvent.click(screen.getByRole('button', { name: 'Delete profile' }));
    await waitFor(() => expect(cameraApi.remove).toHaveBeenCalledWith(profile.id));
    expect(await screen.findByText(/No camera intrinsic profiles saved/)).toBeInTheDocument();
  });

  it("shows server failures while retaining an operational empty form", async () => {
    vi.mocked(cameraApi.profiles).mockRejectedValue(new Error('Local API unavailable'));
    render(<CameraIntrinsics session={initialSession} connected={false} perform={perform} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Local API unavailable');
    expect(screen.getByRole('button', { name: 'Fit and save camera profile' })).toBeDisabled();
    expect(screen.getByLabelText('Import camera profile JSON')).toBeDisabled();
  });
});
