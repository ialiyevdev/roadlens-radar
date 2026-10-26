import { createHash } from "node:crypto";
import { lstat, readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { noticeSources, screenshotNames } from "./prepare_showcase.mjs";

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

async function filesWithin(directory, prefix = "") {
  const files = [];
  for (const entry of await readdir(path.join(directory, prefix), { withFileTypes: true })) {
    const name = prefix ? `${prefix}/${entry.name}` : entry.name;
    const stat = await lstat(path.join(directory, name));
    if (stat.isSymbolicLink() || (entry.isFile() && stat.nlink > 1)) throw new Error(`Links are not allowed in the Pages artifact: ${name}`);
    if (entry.isDirectory()) files.push(...await filesWithin(directory, name));
    else if (entry.isFile()) files.push(name);
    else throw new Error(`Unsupported artifact entry: ${name}`);
  }
  return files;
}

export async function checkShowcase({ directory = path.join(repository, "frontend/dist-showcase"), base = "/roadlens-radar/" } = {}) {
  if (base !== "./" && (!base.startsWith("/") || !base.endsWith("/") || base.includes(".."))) {
    throw new Error("Base must be ./ or a slash-delimited repository path.");
  }
  const files = await filesWithin(directory);
  const notices = new Set(noticeSources.map(([, target]) => `notices/${target}`).concat("notices/README.md"));
  const allowedScreenshots = new Set(screenshotNames.map((name) => `screenshots/${name}`));
  for (const filename of files) {
    const allowed = ["index.html", "favicon.svg"].includes(filename) || notices.has(filename) ||
      allowedScreenshots.has(filename) || /^assets\/[^/]+-[A-Za-z0-9_-]{8}\.(?:js|css|json|svg|png|jpe?g|webp)$/.test(filename);
    if (!allowed || (!notices.has(filename) && /(?:^|\/)(?:App-|\.env|data|models|backend|node_modules)(?:\/|$)/.test(filename))) {
      throw new Error(`Unexpected file in the static-only Pages artifact: ${filename}`);
    }
  }
  for (const filename of ["index.html", "favicon.svg", ...notices, ...allowedScreenshots]) {
    if (!files.includes(filename)) throw new Error(`Required showcase asset is missing: ${filename}`);
  }
  if (!files.some((name) => /^assets\/StaticShowcase-.*\.js$/.test(name)) || files.some((name) => /^assets\/App-/.test(name))) {
    throw new Error("Expected the standalone StaticShowcase bundle without the full application.");
  }
  const manifest = JSON.parse(await readFile(path.join(directory, "notices/examples/demo/manifest.json"), "utf8"));
  for (const name of screenshotNames) {
    const asset = manifest.assets.find((item) => item.filename === `docs/screenshots/${name}`);
    const bytes = await readFile(path.join(directory, "screenshots", name));
    if (!asset || bytes.length !== asset.bytes || createHash("sha256").update(bytes).digest("hex") !== asset.sha256 ||
        !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
      throw new Error(`Packaged screenshot failed integrity verification: ${name}`);
    }
  }
  const page = await readFile(path.join(directory, "index.html"), "utf8");
  const pageReferences = [...page.matchAll(/(?:src|href)=["']([^"']+)["']/g)].map((match) => match[1]);
  if (!pageReferences.length || pageReferences.some((reference) => !reference.startsWith(base))) {
    throw new Error(`HTML asset references do not use the requested base: ${base}`);
  }
  const mount = base === "./" ? "/roadlens-radar/" : base;
  let references = 0;
  function requireAsset(reference, from) {
    if (/^(?:data:|https?:|#)/.test(reference)) return;
    const origin = `https://showcase.invalid${mount}${from}`;
    const url = new URL(reference, origin);
    if (!url.pathname.startsWith(mount)) throw new Error(`Asset escapes the repository base: ${reference}`);
    const filename = decodeURIComponent(url.pathname.slice(mount.length));
    if (!files.includes(filename)) throw new Error(`Referenced showcase asset is missing: ${filename}`);
    references++;
  }
  for (const reference of pageReferences) requireAsset(reference, "index.html");
  for (const filename of files.filter((name) => /\.(?:js|css)$/.test(name))) {
    const content = await readFile(path.join(directory, filename), "utf8");
    if (/\/api(?:\/|["'`])|https?:\/\/(?:localhost|127\.0\.0\.1):8000|navigator\.mediaDevices|getUserMedia/.test(content)) {
      throw new Error(`Backend or camera access appeared in the static bundle: ${filename}`);
    }
    for (const match of content.matchAll(/(?:["'`])((?:\.\/|\/roadlens-radar\/|assets\/)[^\s"'`<>]+?\.(?:js|css|json|png|jpe?g|svg|webp))(?:["'`])/g)) {
      const reference = match[1].startsWith("assets/") ? `${mount}${match[1]}` : match[1];
      requireAsset(reference, filename);
    }
    for (const match of content.matchAll(/new URL\((["'`])([^"'`]+)\1,\s*import\.meta\.url\)/g)) {
      requireAsset(match[2], filename);
    }
  }
  return { files: files.length, references, screenshots: screenshotNames.length, base };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const options = {};
    const args = process.argv.slice(2);
    for (let index = 0; index < args.length; index += 2) {
      if (!["--directory", "--base"].includes(args[index]) || !args[index + 1]) throw new Error("Usage: node scripts/check_showcase.mjs [--directory PATH] [--base /roadlens-radar/|./]");
      options[args[index].slice(2)] = args[index] === "--directory" ? path.resolve(args[index + 1]) : args[index + 1];
    }
    const result = await checkShowcase(options);
    console.log(`Static showcase verified: ${result.files} files, ${result.references} asset references, ${result.screenshots} screenshots, base ${result.base}.`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
