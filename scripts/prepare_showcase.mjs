import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const screenshotNames = [
  "phase6-showcase.png",
  "phase6-showcase-mobile.png",
  "phase6-dashboard.png",
];
export const noticeSources = [
  ["LICENSE", "LICENSE"],
  ["third_party/NOTICE.md", "third_party/NOTICE.md"],
  ["third_party/opencv_yolox_LICENSE.txt", "third_party/opencv_yolox_LICENSE.txt"],
  ["backend/tests/fixtures/README.md", "backend/tests/fixtures/README.md"],
  ["examples/demo/manifest.json", "examples/demo/manifest.json"],
  ["frontend/node_modules/react/LICENSE", "npm/react-LICENSE.txt"],
  ["frontend/node_modules/react-dom/LICENSE", "npm/react-dom-LICENSE.txt"],
  ["frontend/node_modules/scheduler/LICENSE", "npm/scheduler-LICENSE.txt"],
];

export async function prepareShowcase({ root = repository, directory = path.join(root, "frontend/dist-showcase") } = {}) {
  await readFile(path.join(directory, "index.html"));
  const manifest = JSON.parse(await readFile(path.join(root, "examples/demo/manifest.json"), "utf8"));
  const screenshots = [];
  for (const name of screenshotNames) {
    const filename = `docs/screenshots/${name}`;
    const asset = manifest.assets.find((item) => item.filename === filename);
    if (!asset || asset.redistribution_permission !== "permitted_under_declared_license") {
      throw new Error(`Screenshot is not reviewed for redistribution: ${filename}`);
    }
    const bytes = await readFile(path.join(root, filename));
    if (bytes.length !== asset.bytes || createHash("sha256").update(bytes).digest("hex") !== asset.sha256) {
      throw new Error(`Screenshot differs from the reviewed manifest: ${filename}`);
    }
    screenshots.push([name, bytes]);
  }
  // Read every required notice before writing release assets.
  for (const [source] of noticeSources) await readFile(path.join(root, source));
  await mkdir(path.join(directory, "screenshots"), { recursive: true });
  for (const [name, bytes] of screenshots) await writeFile(path.join(directory, "screenshots", name), bytes);
  for (const [source, destination] of noticeSources) {
    const target = path.join(directory, "notices", destination);
    await mkdir(path.dirname(target), { recursive: true });
    await copyFile(path.join(root, source), target);
  }
  await writeFile(path.join(directory, "notices/README.md"),
    "# Showcase distribution notices\n\n" +
    "The interface and synthetic fixtures retain the repository's MIT terms in LICENSE.\n" +
    "Runtime React, React DOM and scheduler licenses are retained under npm/.\n" +
    "The reviewed screenshot manifest is examples/demo/manifest.json.\n" +
    "The dashboard screenshot contains an attributed CC0 photograph; its provenance\n" +
    "is in backend/tests/fixtures/README.md. The other screenshots show synthetic data.\n" +
    "third_party/ retains the model notices for historical reports. No model weights,\n" +
    "Python backend, local recording or private study data is included.\n", "utf8");
  return { screenshots: screenshots.length, notices: noticeSources.length + 1 };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2);
    if (args.length && (args.length !== 2 || args[0] !== "--directory")) throw new Error("Usage: node scripts/prepare_showcase.mjs [--directory PATH]");
    const result = await prepareShowcase(args.length ? { directory: path.resolve(args[1]) } : {});
    console.log(`Prepared ${result.screenshots} reviewed screenshots and ${result.notices} notice files.`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
