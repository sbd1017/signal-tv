// Ambient light: whatever is on screen, spread behind the interface like a TV's backlight.
// A 16x9 canvas is fed the video picture a few times a second (or a poster/logo when nothing is
// playing) and blurred by CSS; each frame is blended over the last, so colour changes drift
// rather than flicker. Its average colour is also published as --amb for small tints.
// Everything is same-origin (the API's image proxy and the app's own streams), so the canvas
// stays readable. Costs ~0.1 ms per frame.

const cv = document.getElementById('ambient');
const ctx = cv.getContext('2d', { willReadFrequently: true });
const root = document.documentElement;
const TOUCH = matchMedia('(hover: none)').matches;
const FRAME_MS = TOUCH ? 330 : 160;

let video = null;          // follow this <video> while it plays
let image = null;          // HTMLImageElement used when no video is playing
let timer = 0;
let fadeLeft = 0;          // image: blend steps remaining
let darkFor = 0;           // consecutive near-black samples while a video plays
let videoBlind = false;    // this browser gives us black frames (e.g. some native-HLS paths)
let lastAvg = 0;

function tick() {
  const playing = video && !video.paused && video.readyState >= 2 && !videoBlind && document.visibilityState === 'visible';
  if (playing) {
    ctx.globalAlpha = 0.28;
    try { ctx.drawImage(video, 0, 0, cv.width, cv.height); } catch { /* not ready */ }
    sample(true);
  } else if (image && fadeLeft > 0) {
    ctx.globalAlpha = 0.22;
    try { ctx.drawImage(image, 0, 0, cv.width, cv.height); } catch { /* broken image */ }
    fadeLeft--;
    if (!fadeLeft) sample(false);
  } else if (!image && !playing) {
    ctx.globalAlpha = 0.12;                      // let the light fade out
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, cv.width, cv.height);
  }
}

function sample(fromVideo) {
  const now = performance.now();
  if (fromVideo && now - lastAvg < 1500) return;
  lastAvg = now;
  let d;
  try { d = ctx.getImageData(0, 0, cv.width, cv.height).data; } catch { return; }
  let r = 0, g = 0, b = 0;
  for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; }
  const n = d.length / 4;
  r /= n; g /= n; b /= n;
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  if (fromVideo) {
    darkFor = lum < 3 ? darkFor + 1 : 0;
    if (darkFor >= 4 && video && video.currentTime > 3) { videoBlind = true; fadeLeft = 12; }
  }
  // a lifted, saturated version of the average for accents (never muddy grey)
  const max = Math.max(r, g, b, 1);
  const k = Math.min(3, 190 / max);
  root.style.setProperty('--amb', `${Math.round(r * k)} ${Math.round(g * k)} ${Math.round(b * k)}`);
}

function ensure() {
  const want = !!(video || image);
  document.body.classList.toggle('amb-on', want);
  if (!timer) timer = setInterval(tick, FRAME_MS);
}

export function follow(v) {
  if (video !== v) { video = v; darkFor = 0; }
  ensure();
}

export function unfollow() {
  video = null;
  if (image) fadeLeft = 14;
  ensure();
}

// Artwork behind the page when no video plays (poster, logo, backdrop). null clears it.
export function art(url) {
  if (!url) { image = null; ensure(); return; }
  if (image && image.dataset.src === url) return;
  const im = new Image();
  im.decoding = 'async';
  im.dataset.src = url;
  im.onload = () => { if (image === im) { fadeLeft = 14; ensure(); } };
  im.src = url;
  image = im;
  ensure();
}

// A new source after a channel switch: black frames from the last one shouldn't count against it.
export function reset() {
  videoBlind = false;
  darkFor = 0;
}
