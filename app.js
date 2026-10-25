const $ = id => document.getElementById(id);
const video = $('video');
let sourceUrl, slowSpeed = 0.25, holding = false, resumePaused = false, heldPointer = null;
const format = seconds => Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}` : '0:00';
function stopSlow() {
  if (!holding) return;
  holding = false;
  video.playbackRate = 1;
  $('stage').classList.remove('slowing');
  if (resumePaused) video.pause();
  heldPointer = null;
}
function startSlow() {
  if (!video.currentSrc || holding || video.readyState < 1 || video.ended) return;
  holding = true;
  resumePaused = video.paused;
  video.playbackRate = slowSpeed;
  $('stage').classList.add('slowing');
  video.play().catch(() => { stopSlow(); $('status').textContent = 'Press Play first, then hold the corner to slow down.'; });
}
function load(file) {
  if (!file) return;
  if (!file.type.startsWith('video/') && !/\.(mp4|webm|mov|m4v|ogv|mkv)$/i.test(file.name)) {
    $('status').textContent = 'Please choose a video file.';
    return;
  }
  stopSlow(); video.pause();
  if (sourceUrl) URL.revokeObjectURL(sourceUrl);
  sourceUrl = URL.createObjectURL(file);
  video.src = sourceUrl; video.load();
  video.classList.add('loaded'); $('empty').hidden = true;
  $('fileName').textContent = file.name;
  ['play', 'hold', 'timeline', 'mute', 'full'].forEach(id => $(id).disabled = true);
  $('timeline').value = 0; $('elapsed').textContent = '0:00';
  $('status').textContent = 'Loading your video…';
}
['choose', 'replace'].forEach(id => $(id).addEventListener('click', () => $('file').click()));
$('file').addEventListener('change', event => { load(event.target.files[0]); event.target.value = ''; });
let dragDepth = 0;
window.addEventListener('dragenter', event => { event.preventDefault(); dragDepth++; $('stage').classList.add('dragging'); });
window.addEventListener('dragover', event => event.preventDefault());
window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; $('stage').classList.remove('dragging'); } });
window.addEventListener('drop', event => { event.preventDefault(); dragDepth = 0; $('stage').classList.remove('dragging'); load(event.dataTransfer.files[0]); });
video.addEventListener('loadedmetadata', () => {
  $('duration').textContent = format(video.duration);
  ['play', 'hold', 'timeline', 'mute', 'full'].forEach(id => $(id).disabled = false);
  $('status').textContent = 'Ready. Press Play, then hold the corner or the S key. Your video stays on your device.';
});
video.addEventListener('error', () => { stopSlow(); $('status').textContent = 'This browser cannot play this video. Try an MP4 (H.264) or WebM file.'; });
function togglePlay() { if (!video.currentSrc) return; if (video.paused) video.play().catch(() => { $('status').textContent = 'Unable to play this video. Try another format.'; }); else video.pause(); }
$('play').addEventListener('click', togglePlay);
video.addEventListener('click', togglePlay);
video.addEventListener('play', () => { $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label', 'Pause'); });
video.addEventListener('pause', () => { $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Play'); });
video.addEventListener('ended', stopSlow);
video.addEventListener('timeupdate', () => { $('elapsed').textContent = format(video.currentTime); $('timeline').value = video.duration ? video.currentTime / video.duration * 100 : 0; });
$('timeline').addEventListener('input', event => { if (Number.isFinite(video.duration)) video.currentTime = event.target.value / 100 * video.duration; });
$('hold').addEventListener('pointerdown', event => { if (event.button !== 0) return; event.preventDefault(); $('hold').setPointerCapture(event.pointerId); startSlow(); heldPointer = event.pointerId; });
['pointerup', 'pointercancel', 'lostpointercapture'].forEach(name => $('hold').addEventListener(name, event => { if (heldPointer === event.pointerId) stopSlow(); }));
$('hold').addEventListener('contextmenu', event => event.preventDefault());
window.addEventListener('keydown', event => {
  if (event.ctrlKey || event.metaKey || event.altKey || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)) return;
  if (event.code === 'KeyS' || (event.target === $('hold') && ['Space', 'Enter'].includes(event.code))) { event.preventDefault(); if (!event.repeat) startSlow(); }
});
window.addEventListener('keyup', event => { if (['KeyS', 'Space', 'Enter'].includes(event.code)) stopSlow(); });
window.addEventListener('blur', stopSlow);
document.addEventListener('visibilitychange', () => { if (document.hidden) stopSlow(); });
document.querySelectorAll('[data-speed]').forEach(button => button.addEventListener('click', () => {
  slowSpeed = Number(button.dataset.speed);
  document.querySelectorAll('[data-speed]').forEach(item => { const active = item === button; item.classList.toggle('selected', active); item.setAttribute('aria-pressed', String(active)); });
  $('liveSpeed').textContent = `${slowSpeed}×`;
  if (holding) video.playbackRate = slowSpeed;
}));
$('mute').addEventListener('click', () => { video.muted = !video.muted; $('mute').textContent = video.muted ? '×' : '♪'; $('mute').setAttribute('aria-label', video.muted ? 'Unmute' : 'Mute'); });
$('full').addEventListener('click', async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else if ($('stage').requestFullscreen) await $('stage').requestFullscreen(); else $('status').textContent = 'Fullscreen is unavailable in this browser.'; } catch { $('status').textContent = 'Fullscreen is unavailable in this browser.'; } });
