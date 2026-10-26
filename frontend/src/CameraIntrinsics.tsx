import { useEffect, useState } from "react";
import { cameraApi } from "./cameraApi";
import type { CameraCalibrationInput, CameraIntrinsicProfile } from "./cameraTypes";
import type { Session } from "./types";
import { errorMessage } from "./useSession";
import "./camera.css";

export function CameraIntrinsics({ session, connected, perform }: {
  session: Session;
  connected: boolean;
  perform: (operation: () => Promise<Session>) => Promise<void>;
}) {
  const [profiles, setProfiles] = useState<CameraIntrinsicProfile[]>([]);
  const [selected, setSelected] = useState("");
  const [configuration, setConfiguration] = useState<CameraCalibrationInput>({
    name: "", camera_configuration_id: "", rotation: 0, mirrored: false, crop: null,
    checkerboard: { inner_columns: 9, inner_rows: 6, square_size_mm: 25 },
    metadata: { camera: "", lens: "", zoom: "", focus: "", notes: "" },
  });
  const [files, setFiles] = useState<File[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<number | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const profile = profiles.find(item => item.id === selected);
  const active = (session.geometry as { intrinsic_profile_id?: string } | null)?.intrinsic_profile_id;
  const observing = session.state === "running" || session.state === "starting";

  useEffect(() => {
    let mounted = true;
    cameraApi.profiles().then(result => {
      if (mounted) setProfiles(result.profiles);
    }).catch(reason => { if (mounted) setError(errorMessage(reason)); });
    return () => { mounted = false; };
  }, []);

  function select(id: string) {
    setSelected(id);
    setConfirmed(false);
    setPreview(null);
    setPreviewError(false);
  }

  async function action(operation: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try { await operation(); } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  function add(result: CameraIntrinsicProfile) {
    setProfiles(current => [...current.filter(item => item.id !== result.id), result]);
    select(result.id);
  }

  const canFit = configuration.name.trim() && configuration.camera_configuration_id.trim()
    && files.length >= 6 && files.length <= 40 && Object.values(configuration.checkerboard).every(Number.isFinite)
    && configuration.checkerboard.inner_columns >= 3 && configuration.checkerboard.inner_rows >= 3
    && configuration.checkerboard.square_size_mm > 0;

  return <section className="camera-intrinsics" aria-labelledby="intrinsics-heading">
    <div className="panel camera-intro">
      <div className="panel-heading"><h2 id="intrinsics-heading">Optional camera intrinsics</h2></div>
      <p>A lens model corrects image geometry. Road-plane calibration maps those pixels to metres. Independent reference events establish speed evidence. Each is a separate step.</p>
      <p>Correction keeps the original frame size and camera matrix, with no crop. Detection, tracks, gates and road references then use corrected pixels. Switching models invalidates the road calibration.</p>
      <p>Pause observation before applying or disabling correction. The capture pipeline currently supports unrotated, unmirrored, uncropped inputs; other geometry can be documented in a profile but cannot be activated.</p>
      <p className="camera-coordinate-status">Current coordinates: <strong>{active ? "undistorted image pixels" : "source image pixels"}</strong>. Black border regions after correction are expected. Reprojection error is a target-fitting diagnostic.</p>
      {error && <p role="alert" className="inline-error">{error}</p>}
    </div>
    <div className="camera-layout">
      <form className="panel camera-form" onSubmit={event => {
        event.preventDefault();
        if (canFit) void action(async () => add(await cameraApi.calibrate(configuration, files)));
      }}>
        <div className="panel-heading"><h2>Fit checkerboard images</h2></div>
        <p>Capture 10–20 sharp views of a flat target at different tilts, distances and positions, including image edges. Keep the same resolution, lens, zoom and focus. Six distinct views are the minimum.</p>
        <label>Profile name<input value={configuration.name} maxLength={120} onChange={event => setConfiguration({ ...configuration, name: event.target.value })} required /></label>
        <label>Camera configuration ID<input value={configuration.camera_configuration_id} maxLength={200} onChange={event => setConfiguration({ ...configuration, camera_configuration_id: event.target.value })} placeholder="window-webcam-1280x720-zoom1" required /></label>
        <div className="camera-form-grid">
          {([['inner_columns', 'Inner columns'], ['inner_rows', 'Inner rows'], ['square_size_mm', 'Square size · mm']] as const).map(([key, label]) =>
            <label key={key}>{label}<input type="number" min={key === 'square_size_mm' ? .01 : 3} max={key === 'square_size_mm' ? 1000 : 20} step={key === 'square_size_mm' ? 'any' : 1} value={Number.isFinite(configuration.checkerboard[key]) ? configuration.checkerboard[key] : ''} onChange={event => setConfiguration({ ...configuration, checkerboard: { ...configuration.checkerboard, [key]: event.target.value === '' ? NaN : Number(event.target.value) } })} required /></label>)}
        </div>
        <p>Count inner corner intersections, rather than squares. A 10 × 7 square board has 9 × 6 inner corners.</p>
        <div className="camera-form-grid">
          {(['camera', 'lens', 'zoom', 'focus'] as const).map(key => <label key={key}>{key[0].toUpperCase()+key.slice(1)}<input value={configuration.metadata[key]} maxLength={key === 'camera' || key === 'lens' ? 200 : 100} onChange={event => setConfiguration({ ...configuration, metadata: { ...configuration.metadata, [key]: event.target.value } })} /></label>)}
          <label>Image rotation<select value={configuration.rotation} onChange={event => setConfiguration({ ...configuration, rotation: Number(event.target.value) as CameraCalibrationInput['rotation'] })}>{[0, 90, 180, 270].map(value => <option key={value} value={value}>{value}°</option>)}</select></label>
          <label className="camera-checkbox"><input type="checkbox" checked={configuration.mirrored} onChange={event => setConfiguration({ ...configuration, mirrored: event.target.checked })} />Images are mirrored</label>
        </div>
        <label>Camera / target notes<textarea value={configuration.metadata.notes} maxLength={2000} onChange={event => setConfiguration({ ...configuration, metadata: { ...configuration.metadata, notes: event.target.value } })} /></label>
        <label>Checkerboard photos<input type="file" accept="image/png,image/jpeg,image/webp,image/bmp" multiple onChange={event => setFiles(Array.from(event.target.files || []))} /></label>
        <p>{files.length} selected · images stay in memory during fitting; only model parameters and image diagnostics are saved. Each image ≤ 8 MiB; total ≤ 64 MiB.</p>
        <button className="button button-primary" type="submit" disabled={!connected || busy || !canFit}>{busy ? "Working…" : "Fit and save camera profile"}</button>
      </form>
      <div className="panel camera-form">
        <div className="panel-heading"><h2>Saved lens models</h2></div>
        <label>Camera intrinsic profile<select value={selected} onChange={event => select(event.target.value)} disabled={busy}><option value="">Select a profile</option>{profiles.map(item => <option key={item.id} value={item.id}>{item.name} · {item.width} × {item.height}</option>)}</select></label>
        {!profiles.length && <p>No camera intrinsic profiles saved. Existing road calibration works without lens correction.</p>}
        <label>Import camera profile JSON<input type="file" accept=".json,application/json" disabled={!connected || busy} onChange={event => {
          const file = event.target.files?.[0];
          if (file) void action(async () => {
            if (file.size > 1024*1024) throw new Error("Camera profile imports are limited to 1 MiB.");
            let parsed: unknown;
            try { parsed = JSON.parse(await file.text()); } catch { throw new Error("Choose a valid camera profile JSON file."); }
            add(await cameraApi.importProfile(parsed));
          });
          event.target.value = '';
        }} /></label>
        {profile && <>
          <dl className="camera-diagnostics">
            <dt>Configuration</dt><dd>{profile.camera_configuration_id}</dd>
            <dt>Target fit RMS</dt><dd>{profile.rms_reprojection_error_px.toFixed(4)} px</dd>
            <dt>Images used / rejected</dt><dd>{profile.used_image_count} / {profile.rejected_image_count}</dd>
            <dt>Evidence</dt><dd>{profile.provenance === 'synthetic' ? 'Synthetic target evidence' : 'Target images; speed accuracy unverified'}</dd>
            <dt>Coordinate policy</dt><dd>Same size, same K, no crop</dd>
          </dl>
          <ul>{profile.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
          <div className="camera-actions"><a className="button button-secondary" href={`/api/camera-profiles/${encodeURIComponent(profile.id)}/export`} download>Export camera JSON</a><button className="button button-secondary" disabled={!connected || busy || active === profile.id} onClick={() => void action(async () => { await cameraApi.remove(profile.id); setProfiles(current => current.filter(item => item.id !== profile.id)); select(''); })}>Delete profile</button></div>
          <label className="camera-checkbox"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />I checked that camera, lens, resolution, zoom, focus, rotation, mirroring and crop match this profile.</label>
          <div className="camera-actions"><button className="button button-primary" disabled={!connected || busy || observing || !confirmed || !session.width || profile.width !== session.width || profile.height !== session.height || profile.rotation !== 0 || profile.mirrored || profile.crop !== null} onClick={() => void action(() => perform(() => cameraApi.activate(profile.id, true)))}>Apply lens correction</button><button className="button button-secondary" disabled={!connected || busy || !session.width} onClick={() => { setPreview(Date.now()); setPreviewError(false); }}>Preview original and corrected</button></div>
          {observing && <p>Pause the source to change its coordinate model.</p>}
          {session.width > 0 && (profile.width !== session.width || profile.height !== session.height) && <p role="alert">Profile resolution differs from the current source. Correction cannot be applied.</p>}
          <details><summary>Per-image fitting diagnostics</summary><div className="table-scroll"><table><thead><tr><th>Image</th><th>Result</th><th>RMS · px</th></tr></thead><tbody>{profile.images.map((image, index) => <tr key={index}><td>{image.filename}</td><td>{image.reason}</td><td>{image.reprojection_error_px?.toFixed(4) ?? '—'}</td></tr>)}</tbody></table></div></details>
        </>}
        <button className="button button-secondary" disabled={!connected || busy || observing || !active} onClick={() => void action(() => perform(() => cameraApi.activate(null)))}>Use source pixels / disable correction</button>
      </div>
    </div>
    {profile && preview != null && <div className="panel camera-preview-panel"><div className="panel-heading"><h2>Current frame comparison</h2></div><p>Compare visible geometry; this preview does not measure improvement in speed accuracy.</p>{previewError && <p role="alert">Frame preview unavailable. Start or pause a matching source and try again.</p>}<div className="camera-preview-grid">{[false, true].map(corrected => <figure key={String(corrected)}><img src={`/api/camera-profiles/${encodeURIComponent(profile.id)}/preview?corrected=${corrected}&revision=${preview}`} alt={corrected ? 'Corrected frame in undistorted pixel coordinates' : 'Original frame in source pixel coordinates'} onError={() => setPreviewError(true)} /><figcaption>{corrected ? 'Undistorted image pixels' : 'Source image pixels'} · {profile.width} × {profile.height}</figcaption></figure>)}</div></div>}
  </section>;
}

export default CameraIntrinsics;
