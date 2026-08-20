import { spawn } from "node:child_process";
import { once } from "node:events";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const baseUrl = process.argv[2] || "http://127.0.0.1:8091";
const root = resolve(import.meta.dirname, "..");
const cloudEvidence = process.argv.includes("--cloud-evidence");
const outputDirectory = cloudEvidence
  ? join(root, "docs", "evidence")
  : join(root, "var", "visual-smoke");
const profileDirectory = join(outputDirectory, "chrome-profile");
const chromeCandidates = [
  process.env.CHROME_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
].filter(Boolean);
const chromePath = chromeCandidates.find(existsSync);

if (!chromePath) throw new Error("Chrome/Chromium not found. Set CHROME_PATH.");
mkdirSync(outputDirectory, { recursive: true });
rmSync(profileDirectory, { recursive: true, force: true });

const chrome = spawn(chromePath, [
  "--headless=new",
  "--no-sandbox",
  "--disable-gpu",
  "--hide-scrollbars",
  "--remote-debugging-port=0",
  `--user-data-dir=${profileDirectory}`,
  "about:blank",
], { stdio: "ignore" });

const delay = (milliseconds) => new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds));

async function readDebuggingPort() {
  const path = join(profileDirectory, "DevToolsActivePort");
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (existsSync(path)) return Number(readFileSync(path, "utf8").split(/\r?\n/)[0]);
    await delay(50);
  }
  throw new Error("Chrome did not expose a DevTools port.");
}

function protocol(webSocketUrl) {
  const socket = new WebSocket(webSocketUrl);
  const pending = new Map();
  let sequence = 0;
  const opened = new Promise((resolveOpened, rejectOpened) => {
    socket.addEventListener("open", resolveOpened, { once: true });
    socket.addEventListener("error", rejectOpened, { once: true });
  });
  socket.addEventListener("message", ({ data }) => {
    const message = JSON.parse(data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve: resolveCall, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolveCall(message.result || {});
  });
  return {
    async send(method, params = {}) {
      await opened;
      sequence += 1;
      socket.send(JSON.stringify({ id: sequence, method, params }));
      return new Promise((resolveCall, reject) => pending.set(sequence, { resolve: resolveCall, reject }));
    },
    close() { socket.close(); },
  };
}

async function inspect(port, name, width, height, hash, interaction = "") {
  const response = await fetch(`http://127.0.0.1:${port}/json/new`, { method: "PUT" });
  if (!response.ok) throw new Error(`Could not create a Chrome target: ${response.status}`);
  const target = await response.json();
  const cdp = protocol(target.webSocketDebuggerUrl);
  await cdp.send("Page.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width <= 560,
    screenWidth: width,
    screenHeight: height,
  });
  await cdp.send("Page.navigate", { url: `${baseUrl}/#${hash}` });
  await delay(1800);
  if (interaction) {
    await cdp.send("Runtime.evaluate", { expression: interaction });
    await delay(600);
  }
  await cdp.send("Runtime.evaluate", {
    expression: `(async () => {
      const images = [...document.images];
      images.forEach(image => { image.loading = 'eager'; });
      await Promise.all(images.map(image => image.complete
        ? Promise.resolve()
        : new Promise(resolveImage => {
            image.addEventListener('load', resolveImage, { once: true });
            image.addEventListener('error', resolveImage, { once: true });
          })));
      window.scrollTo(0, 0);
    })()`,
    awaitPromise: true,
  });
  const evaluation = await cdp.send("Runtime.evaluate", {
    expression: `JSON.stringify({
      innerWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      page: location.hash,
      title: document.querySelector('h1')?.textContent?.trim(),
      images: [...document.images].map(image => ({complete: image.complete, width: image.naturalWidth}))
    })`,
    returnByValue: true,
  });
  const result = JSON.parse(evaluation.result.value);
  const screenshot = await cdp.send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
    fromSurface: true,
  });
  writeFileSync(join(outputDirectory, `${name}.png`), Buffer.from(screenshot.data, "base64"));
  cdp.close();
  if (result.documentWidth > result.innerWidth || result.bodyWidth > result.innerWidth) {
    throw new Error(`${name} has horizontal overflow: ${JSON.stringify(result)}`);
  }
  if (!result.title) throw new Error(`${name} rendered without an h1.`);
  if (result.images.some((image) => !image.complete || image.width === 0)) {
    throw new Error(`${name} contains an unloaded image.`);
  }
  return result;
}

try {
  const port = await readDebuggingPort();
  const results = {
    mobileHome: await inspect(port, "mobile-home", 390, 844, "home"),
    mobileGallery: await inspect(port, "mobile-gallery", 390, 844, "gallery"),
    mobileAsk: await inspect(port, "mobile-ask", 390, 844, "ask"),
    desktopHome: await inspect(port, "desktop-home", 1440, 1000, "home"),
    desktopGallery: await inspect(port, "desktop-gallery", 1440, 1000, "gallery"),
  };
  if (cloudEvidence) {
    results.desktopSources = await inspect(port, "desktop-sources", 1440, 1000, "sources");
    results.desktopLivePhoto = await inspect(
      port,
      "desktop-live-photo",
      1440,
      1000,
      "gallery",
      `document.querySelector('[data-gallery-item^="upload_"]')?.click()`,
    );
  }
  process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
} finally {
  chrome.kill();
  await Promise.race([once(chrome, "exit"), delay(2000)]);
  rmSync(profileDirectory, { recursive: true, force: true });
}
