import { afterEach, describe, expect, it, vi } from 'vitest';
import { cameraApi } from './cameraApi';
import type { CameraCalibrationInput } from './cameraTypes';

afterEach(() => vi.unstubAllGlobals());

describe('camera API', () => {
  it('uses multipart files and configuration without replacing content type', async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 'profile' }) });
    vi.stubGlobal('fetch', fetcher);
    const configuration = { name: 'Target' } as CameraCalibrationInput;
    await cameraApi.calibrate(configuration, [new File(['pixels'], 'target.png')]);
    const [path, options] = fetcher.mock.calls[0];
    expect(path).toBe('/api/camera-profiles/calibrate');
    expect(options.body.get('configuration')).toBe(JSON.stringify(configuration));
    expect(options.body.getAll('files')).toHaveLength(1);
    expect(options.headers).toBeUndefined();
  });
  it('sends explicit unchanged-lens confirmation and supports disabling', async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetcher);
    await cameraApi.activate('profile', true);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ profile_id: 'profile', confirm_unchanged: true });
    await cameraApi.activate(null);
    expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ profile_id: null, confirm_unchanged: false });
  });
  it('shows server validation details and handles proxy failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: [{ msg: 'Invalid matrix' }] }) }));
    await expect(cameraApi.importProfile({})).rejects.toThrow('Invalid matrix');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => { throw new Error('HTML'); } }));
    await expect(cameraApi.profiles()).rejects.toThrow('Camera request failed (502).');
  });
});
