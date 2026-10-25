const $ = id => document.getElementById(id);
const video = $('video');
let sourceUrl, jobId, pollTimer, slowSpeed = .25, holding = false, resumePaused = false;
let heldPointer = null, heldKey = null, holdStart = 0, holds = [], aiReady = false;
let preparing = false, exporting = false, online = false, generation = 0;
let menuIndex = null, menuTrigger = null, exportScope = 'full', supportsSectionExport = false;
const livePlayer = new LiveSlowPlayer(video, $('aiVideo'), (path, body) => api(path, body === undefined ? {} : {
  method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' }
}), {
  state(state, message) {
    $('bufferTag').hidden = state !== 'buffering';
    $('aiLabel').textContent = state === 'buffering' ? 'GPU generating frames on demand' : state === 'playing' ? 'AI slow motion · live GPU windows' : 'AI engine standing by';
    $('aiMessage').textContent = message;
    $('aiDetail').textContent = state === 'idle' ? 'No AI work until you hold' : 'RIFE · smooth 540p preview';
    if (state === 'playing') { $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label', 'Pause'); }
  },
  position(position) { showPosition(position); },
  end() { stopSlow(); },
  error(error) { stopSlow(); $('status').textContent = error.message; }
});
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
  document.querySelectorAll('.section-chip, .section-more').forEach(button => { button.disabled = holding || exporting; });
}
function showPosition(position) {
  $('elapsed').textContent = format(position);
  $('timeline').value = video.duration ? position / video.duration * 100 : 0;
}
function invalidateDownload() { $('download').hidden = true; $('exportInfo').textContent = 'Right-click a section to save just that clip, or save the full video.'; }
function closeSectionMenu(restoreFocus = false) {
  $('sectionMenu').hidden = true; menuIndex = null;
  if (restoreFocus && menuTrigger?.isConnected) menuTrigger.focus();
}
function openSectionMenu(index, trigger, x, y) {
  if (holding || exporting || !holds[index]) return;
  menuIndex = index; menuTrigger = trigger;
  const menu = $('sectionMenu');
  (document.fullscreenElement || document.body).append(menu);
  menu.hidden = false;
  const bounds = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(x, innerWidth - bounds.width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(y, innerHeight - bounds.height - 8))}px`;
  $('saveSection').focus();
}
document.addEventListener('pointerdown', event => { if (!$('sectionMenu').contains(event.target)) closeSectionMenu(); });
document.addEventListener('keydown', event => {
  if ($('sectionMenu').hidden) return;
  if (event.key === 'Escape') { event.preventDefault(); closeSectionMenu(true); }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); (document.activeElement === $('saveSection') ? $('removeSection') : $('saveSection')).focus(); }
  if (event.key === 'Tab') closeSectionMenu();
});
window.addEventListener('resize', () => closeSectionMenu());
document.addEventListener('wheel', () => closeSectionMenu(), { passive: true });
document.addEventListener('touchmove', () => closeSectionMenu(), { passive: true });
$('saveSection').addEventListener('click', () => { const index = menuIndex; closeSectionMenu(); if (index !== null) startExport(index); });
$('removeSection').addEventListener('click', () => { const index = menuIndex; closeSectionMenu(); if (index !== null) { holds.splice(index, 1); invalidateDownload(); renderHolds(); } });
function renderHolds() {
  closeSectionMenu();
  $('sections').replaceChildren();
  holds.forEach((hold, index) => {
    const group = document.createElement('span'); group.className = 'section-group';
    const button = document.createElement('button');
    button.className = 'section-chip';
    button.textContent = `${precise(hold.start)}–${precise(hold.end)} · ${hold.speed === .25 ? '¼' : '½'}×`;
    button.setAttribute('aria-label', `Section ${index + 1} actions, ${precise(hold.start)} to ${precise(hold.end)}`);
    button.setAttribute('aria-haspopup', 'menu');
    button.disabled = exporting || holding;
    button.addEventListener('click', () => { const box = button.getBoundingClientRect(); openSectionMenu(index, button, box.left, box.bottom + 5); });
    button.addEventListener('contextmenu', event => { event.preventDefault(); openSectionMenu(index, button, event.clientX, event.clientY); });
    const more = document.createElement('button'); more.className = 'section-more'; more.textContent = '⋯';
    more.setAttribute('aria-label', `More actions for section ${index + 1}`); more.setAttribute('aria-haspopup', 'menu');
    more.addEventListener('click', () => { const box = more.getBoundingClientRect(); openSectionMenu(index, more, box.left, box.bottom + 5); });
    group.append(button, more); $('sections').append(group);
  });
  $('editHint').textContent = holds.length ? `${holds.length} section${holds.length === 1 ? '' : 's'} marked. Right-click a section or tap ⋯ to save only that clip.` : 'Hold the corner during playback to mark a section.';
  availability();
}
function stopSlow() {
  if (!holding) return;
  const end = Math.min(livePlayer.stop(), video.duration);
  holding = false;
  video.playbackRate = 1;
  $('stage').classList.remove('slowing');
  video.currentTime = end;
  if (resumePaused) video.pause();
  else if (end < video.duration - .001) video.play().catch(() => {});
  if (video.paused) { $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Play'); }
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
  video.playbackRate = 1;
  $('stage').classList.add('slowing');
  availability();
  livePlayer.begin(holdStart, slowSpeed);
  return true;
}
function browserCanPlay(file) {
  return new Promise(resolve => {
    const probe = document.createElement('video'), url = URL.createObjectURL(file);
    const finish = result => {
      clearTimeout(timer); probe.onloadeddata = probe.onerror = null;
      probe.removeAttribute('src'); probe.load(); URL.revokeObjectURL(url); resolve(result);
    };
    const timer = setTimeout(() => finish(false), 6000);
    probe.preload = 'auto'; probe.muted = true;
    probe.onloadeddata = () => finish(true); probe.onerror = () => finish(false);
    probe.src = url; probe.load();
  });
}
function uploadFile(file, onProgress, direct) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', '/api/upload');
    request.setRequestHeader('X-Moment-Client', '1');
    request.setRequestHeader('Content-Type', 'application/octet-stream');
    request.setRequestHeader('X-Moment-Direct', direct ? '1' : '0');
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
  try {
    const health = await api('/api/health');
    if (health.apiVersion !== 5) { $('status').textContent = 'An older engine is running. Open Start Moment.cmd to update it before uploading.'; return; }
  } catch { $('status').textContent = 'The local engine is offline. Open Start Moment.cmd, then reload this page.'; return; }
  if (preparing || exporting) return;
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
  $('progress').removeAttribute('value'); $('aiLabel').textContent = 'Checking playback support';
  $('aiMessage').textContent = 'Playable videos use the original file directly.';
  $('status').textContent = 'AI generation starts only when you hold.';
  try {
    const direct = await browserCanPlay(file);
    if (version !== generation) return;
    $('aiLabel').textContent = 'Copying video to your local engine';
    $('aiMessage').textContent = direct ? 'Browser playback supported. No conversion will run.' : 'This format needs a browser-compatible copy.';
    const result = await uploadFile(file, percent => { $('progress').value = percent; $('aiDetail').textContent = `${Math.round(percent)}% transferred locally`; }, direct);
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
    if (job.progress == null) $('progress').removeAttribute('value'); else $('progress').value = job.progress;
    $('aiMessage').textContent = job.message;
    $('aiLabel').textContent = job.phase === 'ready' ? 'AI engine standing by' : job.phase === 'error' ? 'Video preparation failed' : job.phase === 'converting' ? 'Converting for browser compatibility' : 'Reading video metadata';
    $('aiDetail').textContent = job.phase === 'ready' ? (job.directPlayback ? 'Original video · no conversion' : 'GPU starts on hold') : job.progress == null ? 'Checking…' : `${Math.round(job.progress)}%`;
    if (job.phase === 'ready' && !aiReady) {
      preparing = false; aiReady = true;
      livePlayer.configure(jobId, job.duration);
      const position = video.currentTime || 0, paused = video.paused;
      if (!job.directPlayback || !sourceUrl) {
        video.pause(); video.src = job.preview;
        video.addEventListener('loadedmetadata', () => {
          video.currentTime = Math.min(position, Math.max(0, video.duration - .05));
          if (!paused) video.play().catch(() => {});
        }, { once: true });
        video.load();
      }
      video.classList.add('loaded'); $('empty').hidden = true;
      $('status').textContent = 'Ready. Hold the corner or S to generate AI slow motion at this moment. The first window may buffer.';
      availability();
    }
    if (job.phase === 'error') { preparing = false; aiReady = false; availability(); return; }
    if (exporting) {
      if (job.exportState === 'ready') {
        exporting = false;
        $('download').href = job.download; $('download').hidden = false;
        $('exportInfo').textContent = exportScope === 'section' ? 'Your slow-motion section is ready. No other footage is included.' : 'Your full edited video is ready.';
        $('download').textContent = exportScope === 'section' ? 'Download section MP4 ↓' : 'Download full MP4 ↓';
        $('save').textContent = 'Save full video ↓'; renderHolds();
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
async function startExport(sectionIndex = null) {
  if (!jobId || !holds.length || exporting) return;
  if (sectionIndex !== null && (!supportsSectionExport || !holds[sectionIndex])) {
    $('exportInfo').textContent = 'Restart Moment with Stop Moment.cmd and Start Moment.cmd to enable section-only export.'; return;
  }
  exportScope = sectionIndex === null ? 'full' : 'section';
  const selected = sectionIndex === null ? holds.slice() : [holds[sectionIndex]];
  stopSlow(); video.pause(); exporting = true; invalidateDownload(); renderHolds();
  $('exportInfo').textContent = exportScope === 'section' ? 'Saving only the selected slow-motion section…' : 'Saving the full edited video…';
  $('save').textContent = 'Rendering…';
  try { await api(`/api/export/${jobId}`, { method: 'POST', body: JSON.stringify({ holds: selected, scope: exportScope }), headers: { 'Content-Type': 'application/json' } }); poll(generation); }
  catch (error) { exporting = false; $('exportInfo').textContent = error.message; $('save').textContent = 'Retry save ↓'; renderHolds(); }
}
$('save').addEventListener('click', () => startExport());
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
function togglePlay() { if (!video.currentSrc) return; if (holding) { stopSlow(); video.pause(); } else if (video.paused) video.play().catch(() => { $('status').textContent = 'Unable to play this video. Try another format.'; }); else video.pause(); }
$('play').addEventListener('click', togglePlay);
video.addEventListener('click', togglePlay);
[video, $('aiVideo')].forEach(player => player.addEventListener('contextmenu', event => {
  if (exporting) return;
  if (holding) stopSlow();
  const position = video.currentTime;
  const index = holds.findLastIndex(hold => position >= hold.start - .001 && position <= hold.end + 1 / 30);
  if (index < 0) return;
  event.preventDefault(); video.pause();
  openSectionMenu(index, player, event.clientX, event.clientY);
}));
video.addEventListener('play', () => { $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label', 'Pause'); });
video.addEventListener('pause', () => { $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Play'); });
video.addEventListener('ended', stopSlow);
video.addEventListener('timeupdate', () => { if (!holding) showPosition(video.currentTime); });
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
$('mute').addEventListener('click', () => { video.muted = !video.muted; $('aiVideo').muted = video.muted; $('mute').textContent = video.muted ? '×' : '♪'; $('mute').setAttribute('aria-label', video.muted ? 'Unmute' : 'Mute'); });
$('full').addEventListener('click', async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else if ($('stage').requestFullscreen) await $('stage').requestFullscreen(); else $('status').textContent = 'Fullscreen is unavailable in this browser.'; } catch { $('status').textContent = 'Fullscreen is unavailable in this browser.'; } });
async function init() {
  try {
    const health = await api('/api/health'); online = health.engine;
    if (health.apiVersion !== 5) {
      online = false; $('aiLabel').textContent = 'Engine update needed';
      $('aiMessage').textContent = 'Open Start Moment.cmd to load the smooth playback engine, then refresh this page.';
      availability(); return;
    }
    supportsSectionExport = health.sectionExport === true;
    $('aiLabel').textContent = online ? 'RIFE engine connected' : 'RIFE engine is missing';
    $('aiMessage').textContent = 'Load a video for normal playback. Hold the corner to start GPU frame generation exactly where you are watching.';
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
