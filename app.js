const $ = id => document.getElementById(id);
const video = $('video');
let sourceUrl, jobId, pollTimer, slowSpeed = .25, holding = false, resumePaused = false;
let heldPointer = null, heldKey = null, holdStart = 0, holds = [], aiReady = false;
let preparing = false, exporting = false, online = false, generation = 0;
const format = seconds => Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}` : '0:00';
const precise = seconds => `${format(seconds)}.${Math.floor((seconds % 1) * 10)}`;

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'X-Moment-Client': '1', ...options.headers } });
  const body = await response.json();
  if (!response.ok) throw new Error(body.message || 'Request failed.');
  return body;
}
function availability() {
  $('hold').disabled = !aiReady || exporting;
  $('replace').disabled = preparing || exporting || !online;
  $('choose').disabled = preparing || !online;
  $('save').disabled = !aiReady || !holds.length || exporting || holding;
  $('clear').disabled = !holds.length || exporting || holding;
  document.querySelectorAll('[data-speed]').forEach(button => { button.disabled = holding; });
}
function invalidateDownload() { $('download').hidden = true; $('exportInfo').textContent = 'Save keeps the full video, with your marked sections slowed down.'; }
function renderHolds() {
  $('sections').replaceChildren();
  holds.forEach((hold, index) => {
    const button = document.createElement('button');
    button.className = 'section-chip';
    button.textContent = `${precise(hold.start)}–${precise(hold.end)} · ${hold.speed === .25 ? '¼' : '½'}×  ×`;
    button.setAttribute('aria-label', `Remove slow section ${index + 1}, ${precise(hold.start)} to ${precise(hold.end)}`);
    button.disabled = exporting || holding;
    button.addEventListener('click', () => { holds.splice(index, 1); invalidateDownload(); renderHolds(); });
    $('sections').append(button);
  });
  $('editHint').textContent = holds.length ? `${holds.length} section${holds.length === 1 ? '' : 's'} marked. New holds replace overlapping parts when saved.` : 'Hold the corner during playback to mark a section.';
  availability();
}
function stopSlow() {
  if (!holding) return;
  const end = Math.min(video.currentTime, video.duration);
  holding = false;
  video.playbackRate = 1;
  $('stage').classList.remove('slowing');
  if (resumePaused) video.pause();
  if (end - holdStart >= 1 / 30) {
    holds.push({ start: holdStart, end, speed: slowSpeed });
    invalidateDownload();
  }
  heldPointer = null; heldKey = null;
  renderHolds();
}
function startSlow() {
  if (!aiReady || exporting || holding || video.readyState < 1 || video.ended) return false;
  if (holds.length >= 50) { $('status').textContent = '50 sections marked. Save or remove a section before adding more.'; return false; }
  holding = true; holdStart = video.currentTime; resumePaused = video.paused;
  video.playbackRate = slowSpeed;
  $('stage').classList.add('slowing');
  availability();
  video.play().catch(() => { stopSlow(); $('status').textContent = 'Press Play first, then hold the corner to slow down.'; });
  return true;
}
function uploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', '/api/upload');
    request.setRequestHeader('X-Moment-Client', '1');
    request.setRequestHeader('Content-Type', 'application/octet-stream');
    request.upload.onprogress = event => { if (event.lengthComputable) onProgress(event.loaded / event.total * 100); };
    request.onload = () => {
      try { const body = JSON.parse(request.responseText); if (request.status >= 400) reject(new Error(body.message)); else resolve(body); }
      catch { reject(new Error('The local server returned an invalid response.')); }
    };
    request.onerror = () => reject(new Error('Cannot connect to the local engine. Open Start Moment.cmd.'));
    request.send(file);
  });
}
async function load(file) {
  if (!file) return;
  if (preparing || exporting) { $('status').textContent = 'Please wait for the current job to finish before changing videos.'; return; }
  if (!online) { $('status').textContent = 'Open Start Moment.cmd to connect to the AI engine.'; return; }
  if (!file.type.startsWith('video/') && !/\.(mp4|webm|mov|m4v|ogv|mkv)$/i.test(file.name)) { $('status').textContent = 'Please choose a video file.'; return; }
  if (file.size > 1024 ** 3) { $('status').textContent = 'Please choose a video smaller than 1 GB.'; return; }
  stopSlow(); video.pause(); clearTimeout(pollTimer);
  const version = ++generation;
  aiReady = false; preparing = true; holds = []; jobId = null;
  localStorage.removeItem('moment-job'); invalidateDownload(); renderHolds();
  if (sourceUrl) URL.revokeObjectURL(sourceUrl);
  sourceUrl = URL.createObjectURL(file); video.src = sourceUrl; video.load();
  video.classList.add('loaded'); $('empty').hidden = true;
  ['play', 'timeline', 'mute', 'full'].forEach(id => $(id).disabled = true);
  $('fileName').textContent = file.name;
  $('timeline').value = 0; $('elapsed').textContent = '0:00';
  $('progress').value = 0; $('aiLabel').textContent = 'Sending video to your local engine';
  $('aiMessage').textContent = 'Your video is sent only to the server on this PC.';
  $('status').textContent = 'Ordinary playback is available while AI frames are prepared. Hold-to-slow unlocks when ready.';
  try {
    const result = await uploadFile(file, percent => { $('progress').value = percent; $('aiDetail').textContent = `${Math.round(percent)}% transferred locally`; });
    if (version !== generation) return;
    jobId = result.id;
    localStorage.setItem('moment-job', JSON.stringify({ id: jobId, name: file.name }));
    poll(version);
  } catch (error) { preparing = false; $('aiLabel').textContent = 'Preparation failed'; $('aiMessage').textContent = error.message; availability(); }
}
async function poll(version) {
  try {
    const job = await api(`/api/jobs/${jobId}`);
    if (version !== generation) return;
    $('progress').value = job.progress || 0;
    $('aiMessage').textContent = job.message;
    $('aiLabel').textContent = ({ queued: 'Queued for local GPU', decoding: 'Preparing source frames', interpolating: 'RIFE · generating intermediate frames', encoding: 'Encoding smooth preview', ready: '✦ AI frames ready · 120 fps preview', error: 'Preparation failed' })[job.phase] || job.phase;
    $('aiDetail').textContent = job.inferenceFps ? `${job.inferenceFps} frames/s · ${job.phase === 'ready' ? `${job.inferenceSeconds}s AI processing` : `${job.generatedFrames || 0}/${job.outputFrames}`}` : `${Math.round(job.progress || 0)}%`;
    if (job.phase === 'ready' && !aiReady) {
      preparing = false; aiReady = true;
      const position = video.currentTime || 0, paused = video.paused;
      video.pause();
      video.src = job.preview;
      video.addEventListener('loadedmetadata', () => {
        video.currentTime = Math.min(position, Math.max(0, video.duration - .05));
        if (!paused) video.play().catch(() => {});
      }, { once: true });
      video.load(); video.classList.add('loaded'); $('empty').hidden = true;
      $('status').textContent = 'Ready: AI-generated frames at ¼× or ½×. Hold the corner or S, then save your marked sections.';
      availability();
    }
    if (job.phase === 'error') { preparing = false; aiReady = false; availability(); return; }
    if (exporting) {
      if (job.exportState === 'ready') {
        exporting = false;
        $('download').href = job.download; $('download').hidden = false;
        $('exportInfo').textContent = 'Your MP4 is ready. Download it to keep your edit.';
        $('save').textContent = 'Save MP4 ↓'; renderHolds();
      } else if (job.exportState === 'error') {
        exporting = false; $('exportInfo').textContent = job.exportMessage;
        $('save').textContent = 'Retry save ↓'; renderHolds();
      } else $('exportInfo').textContent = `Rendering MP4 on your PC… ${job.exportProgress || 0}%`;
    }
    if (preparing || exporting) pollTimer = setTimeout(() => poll(version), 1000);
  } catch (error) {
    if (version !== generation) return;
    preparing = false; exporting = false; aiReady = false;
    $('aiLabel').textContent = 'Connection lost'; $('aiMessage').textContent = `${error.message} Reopen Start Moment.cmd and reload this page.`;
    availability();
  }
}
$('save').addEventListener('click', async () => {
  if (!jobId || !holds.length || exporting) return;
  stopSlow(); video.pause(); exporting = true; invalidateDownload(); renderHolds();
  $('save').textContent = 'Rendering…';
  try { await api(`/api/export/${jobId}`, { method: 'POST', body: JSON.stringify({ holds }), headers: { 'Content-Type': 'application/json' } }); poll(generation); }
  catch (error) { exporting = false; $('exportInfo').textContent = error.message; $('save').textContent = 'Retry save ↓'; renderHolds(); }
});
$('clear').addEventListener('click', () => { holds = []; invalidateDownload(); renderHolds(); });
['choose', 'replace'].forEach(id => $(id).addEventListener('click', () => $('file').click()));
$('file').addEventListener('change', event => { load(event.target.files[0]); event.target.value = ''; });
let dragDepth = 0;
window.addEventListener('dragenter', event => { event.preventDefault(); dragDepth++; $('stage').classList.add('dragging'); });
window.addEventListener('dragover', event => event.preventDefault());
window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; $('stage').classList.remove('dragging'); } });
window.addEventListener('drop', event => { event.preventDefault(); dragDepth = 0; $('stage').classList.remove('dragging'); load(event.dataTransfer.files[0]); });
video.addEventListener('loadedmetadata', () => {
  $('duration').textContent = format(video.duration);
  ['play', 'timeline', 'mute', 'full'].forEach(id => $(id).disabled = false);
});
video.addEventListener('error', () => { if (aiReady) { aiReady = false; availability(); } $('status').textContent = preparing ? 'The browser cannot preview this source format. The engine will try converting it.' : 'This browser cannot play the video. Try another MP4 or WebM.'; });
function togglePlay() { if (!video.currentSrc) return; if (video.paused) video.play().catch(() => { $('status').textContent = 'Unable to play this video. Try another format.'; }); else { stopSlow(); video.pause(); } }
$('play').addEventListener('click', togglePlay);
video.addEventListener('click', togglePlay);
video.addEventListener('play', () => { $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label', 'Pause'); });
video.addEventListener('pause', () => { $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Play'); });
video.addEventListener('ended', stopSlow);
video.addEventListener('timeupdate', () => { $('elapsed').textContent = format(video.currentTime); $('timeline').value = video.duration ? video.currentTime / video.duration * 100 : 0; });
$('timeline').addEventListener('input', event => { stopSlow(); if (Number.isFinite(video.duration)) video.currentTime = event.target.value / 100 * video.duration; });
$('hold').addEventListener('pointerdown', event => { if (event.button !== 0) return; event.preventDefault(); if (startSlow()) { heldPointer = event.pointerId; $('hold').setPointerCapture(event.pointerId); } });
['pointerup', 'pointercancel', 'lostpointercapture'].forEach(name => $('hold').addEventListener(name, event => { if (heldPointer === event.pointerId) stopSlow(); }));
$('hold').addEventListener('contextmenu', event => event.preventDefault());
window.addEventListener('keydown', event => {
  if (event.ctrlKey || event.metaKey || event.altKey || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)) return;
  if (event.code === 'KeyS' || (event.target === $('hold') && ['Space', 'Enter'].includes(event.code))) { event.preventDefault(); if (!event.repeat && startSlow()) heldKey = event.code; }
});
window.addEventListener('keyup', event => { if (event.code === heldKey) stopSlow(); });
window.addEventListener('blur', stopSlow);
document.addEventListener('visibilitychange', () => { if (document.hidden) stopSlow(); });
document.querySelectorAll('[data-speed]').forEach(button => button.addEventListener('click', () => {
  if (holding) return;
  slowSpeed = Number(button.dataset.speed);
  document.querySelectorAll('[data-speed]').forEach(item => { const active = item === button; item.classList.toggle('selected', active); item.setAttribute('aria-pressed', String(active)); });
  $('liveSpeed').textContent = `${slowSpeed}×`;
}));
$('mute').addEventListener('click', () => { video.muted = !video.muted; $('mute').textContent = video.muted ? '×' : '♪'; $('mute').setAttribute('aria-label', video.muted ? 'Unmute' : 'Mute'); });
$('full').addEventListener('click', async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else if ($('stage').requestFullscreen) await $('stage').requestFullscreen(); else $('status').textContent = 'Fullscreen is unavailable in this browser.'; } catch { $('status').textContent = 'Fullscreen is unavailable in this browser.'; } });
async function init() {
  try {
    const health = await api('/api/health'); online = health.engine;
    $('aiLabel').textContent = online ? 'RIFE engine connected' : 'RIFE engine is missing';
    $('aiMessage').textContent = 'Choose a video to generate 3 AI frames between each pair. Initial preparation takes time.';
    const remembered = JSON.parse(localStorage.getItem('moment-job') || 'null');
    if (online && remembered) {
      const job = await api(`/api/jobs/${remembered.id}`).catch(() => null);
      if (job && job.phase !== 'error') {
        jobId = remembered.id; preparing = true;
        $('fileName').textContent = remembered.name; poll(generation);
      } else localStorage.removeItem('moment-job');
    }
  } catch { $('aiLabel').textContent = 'Local engine is offline'; $('aiMessage').textContent = 'Close this tab and open Start Moment.cmd in the project folder.'; }
  availability();
}
init();
