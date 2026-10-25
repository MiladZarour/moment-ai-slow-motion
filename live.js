/* Append AI windows to one MediaSource: no video-src reload at window boundaries. */
class LiveSlowPlayer {
  constructor(source, overlay, request, callbacks) {
    this.source = source; this.overlay = overlay; this.request = request; this.callbacks = callbacks;
    this.session = null; this.job = null; this.duration = 0; this.position = 0; this.base = 0;
    this.pending = new Map(); this.started = false; this.ending = false; this.speed = .25;
    this.windowSeconds = .5;
    this.metrics = { stalls: 0, stallSeconds: 0, appended: 0 };
    overlay.addEventListener('timeupdate', () => this.tick());
    overlay.addEventListener('waiting', () => {
      if (!this.session || !this.started || this.ending) return;
      this.source.pause();
      if (!this.waitStarted) {
        this.waitStarted = performance.now(); this.metrics.stalls++;
        this.waitNotice = setTimeout(() => {
          if (this.session && this.waitStarted) this.callbacks.state('buffering', 'GPU is catching up. Keeping the video and audio together…');
        }, 120);
      }
    });
    overlay.addEventListener('playing', () => {
      if (!this.session || !this.started) return;
      clearTimeout(this.waitNotice);
      if (this.waitStarted) { this.metrics.stallSeconds += (performance.now() - this.waitStarted) / 1000; this.waitStarted = null; }
      this.syncAudio(true);
      this.callbacks.state('playing', 'Continuous AI playback · 540p smooth preview · saved clips render up to 720p');
    });
    overlay.addEventListener('ended', () => { if (this.session && this.ending) callbacks.end(); });
  }
  configure(job, duration, windowSeconds = .5) { this.stop(); this.job = job; this.duration = duration; this.windowSeconds = windowSeconds; }
  currentTime() { return this.session && this.started ? Math.min(this.duration, this.base + this.overlay.currentTime) : this.position; }
  tick() {
    if (!this.session || !this.started) return;
    this.position = this.currentTime(); this.callbacks.position(this.position);
    this.callbacks.buffer?.(this.bufferedAhead());
    if (!this.overlay.paused && this.overlay.readyState >= 3) this.syncAudio(false);
  }
  syncAudio(force) {
    if (!this.session || !this.started) return;
    const position = this.currentTime();
    if (force || Math.abs(this.source.currentTime - position) > .15) this.source.currentTime = position;
    this.source.playbackRate = this.speed;
    if (this.source.paused && !this.overlay.paused) this.source.play().catch(() => {});
  }
  async begin(position, speed) {
    if (!window.MediaSource || !MediaSource.isTypeSupported('video/mp4; codecs="avc1.42c02a"')) {
      this.callbacks.error(new Error('Smooth AI playback requires a current Chrome or Edge browser.')); return;
    }
    this.source.pause(); this.position = position; this.speed = speed;
    const windowSeconds = this.windowSeconds;
    this.base = Math.floor((position + 1e-8) / windowSeconds) * windowSeconds; this.started = false; this.ending = false;
    this.metrics = { stalls: 0, stallSeconds: 0, appended: 0 }; this.waitStarted = null;
    this.pending = new Map();
    const session = crypto.randomUUID(), job = this.job;
    this.session = session;
    this.callbacks.state('buffering', 'Building a short AI buffer for continuous playback. Keep holding…');
    try {
      await this.request(`/api/live/${job}`, { session, active: true });
      if (session !== this.session) return;
      const media = new MediaSource(); this.media = media;
      const url = URL.createObjectURL(media); this.mediaUrl = url;
      const opened = new Promise(resolve => media.addEventListener('sourceopen', resolve, { once: true }));
      this.overlay.src = url; this.overlay.muted = true; this.overlay.load();
      await opened;
      if (session !== this.session) return;
      media.duration = Math.max(0, this.duration - this.base);
      const buffer = media.addSourceBuffer('video/mp4; codecs="avc1.42c02a"');
      buffer.mode = 'sequence'; this.buffer = buffer;
      // One initial second of source time gives the GPU room to stay ahead.
      const minimum = Math.min(this.duration - position, 1);
      let index = Math.floor((position + 1e-8) / windowSeconds);
      while (session === this.session && index * windowSeconds < this.duration - .001) {
        while (session === this.session && this.started && this.bufferedAhead() > 3) await this.delay(60);
        if (session !== this.session) return;
        const chunk = await this.ensure(index, session);
        if (session !== this.session) return;
        const response = await fetch(chunk.url);
        if (!response.ok) throw new Error('Could not load generated AI frames.');
        const bytes = await response.arrayBuffer();
        if (session !== this.session) return;
        await this.append(buffer, bytes, session);
        if (session !== this.session) return;
        this.metrics.appended++; index++; this.pending.delete(index - 16);
        const end = buffer.buffered.length ? buffer.buffered.end(buffer.buffered.length - 1) : 0;
        if (!this.started && end - (position - this.base) >= minimum - .012) {
          this.overlay.currentTime = position - this.base;
          this.overlay.playbackRate = speed; this.started = true;
          this.overlay.classList.add('loaded'); await this.overlay.play();
          this.syncAudio(true);
          this.callbacks.state('playing', 'Continuous AI playback · 540p smooth preview · saved clips render up to 720p');
        }
        if (index * windowSeconds >= this.duration - .001) {
          this.ending = true;
          if (media.readyState === 'open' && !buffer.updating) media.endOfStream();
          if (!this.started) {
            this.overlay.currentTime = position - this.base; this.overlay.playbackRate = speed;
            this.started = true; this.overlay.classList.add('loaded'); await this.overlay.play(); this.syncAudio(true);
          }
          return;
        }
        // Fetch the next window immediately. Server batches model work ahead while held.
        this.ensure(index, session).catch(() => {});
        // Bound memory on very long holds. Keep the last 4 seconds for decoder context.
        if (this.started && this.overlay.currentTime > 8 && !buffer.updating) {
          await this.remove(buffer, this.overlay.currentTime - 4, session);
        }
      }
    } catch (error) { if (session === this.session) this.callbacks.error(error); }
  }
  bufferedAhead() {
    const ranges = this.overlay.buffered;
    return ranges.length ? ranges.end(ranges.length - 1) - this.overlay.currentTime : 0;
  }
  delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
  async ensure(index, session) {
    if (session !== this.session) throw new Error('Hold released.');
    if (this.pending.has(index)) return this.pending.get(index);
    const job = this.job;
    const promise = (async () => {
      let chunk = await this.request(`/api/chunks/${job}`, { index, session });
      while (chunk.phase !== 'ready') {
        if (session !== this.session) throw new Error('Hold released.');
        if (['error', 'cancelled'].includes(chunk.phase)) throw new Error(chunk.message || 'Generation cancelled.');
        await this.delay(60); chunk = await this.request(`/api/chunks/${job}/${index}`);
      }
      return chunk;
    })();
    this.pending.set(index, promise); return promise;
  }
  append(buffer, bytes, session) {
    return new Promise((resolve, reject) => {
      if (session !== this.session) return resolve();
      const cleanup = () => { buffer.removeEventListener('updateend', done); buffer.removeEventListener('error', fail); };
      const done = () => { cleanup(); resolve(); };
      const fail = () => { cleanup(); reject(new Error('The continuous AI buffer could not decode this window.')); };
      buffer.addEventListener('updateend', done); buffer.addEventListener('error', fail);
      try { buffer.appendBuffer(bytes); } catch (error) { cleanup(); reject(error); }
    });
  }
  remove(buffer, end, session) {
    return new Promise(resolve => {
      if (session !== this.session) return resolve();
      buffer.addEventListener('updateend', resolve, { once: true }); buffer.remove(0, end);
    });
  }
  stop() {
    const position = this.currentTime(), session = this.session, job = this.job;
    this.session = null; this.started = false; this.ending = false;
    clearTimeout(this.waitNotice); this.waitStarted = null;
    if (session) this.source.pause();
    this.overlay.pause(); this.overlay.classList.remove('loaded');
    this.overlay.removeAttribute('src'); this.overlay.load();
    if (this.mediaUrl) { URL.revokeObjectURL(this.mediaUrl); this.mediaUrl = null; }
    this.media = null; this.buffer = null;
    if (session) this.request(`/api/live/${job}`, { session, active: false }).catch(() => {});
    this.callbacks.state('idle', 'Ready. GPU interpolation starts on your next hold.');
    return position;
  }
}
