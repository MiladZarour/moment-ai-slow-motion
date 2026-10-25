/* Demand-driven GPU windows. No chunk requests are made before begin(). */
class LiveSlowPlayer {
  constructor(source, overlay, request, callbacks) {
    this.source = source; this.overlay = overlay; this.request = request; this.callbacks = callbacks;
    this.session = null; this.job = null; this.pending = new Map(); this.chunk = null;
    this.position = 0; this.duration = 0; this.speed = .25; this.switching = false;
    overlay.addEventListener('ended', () => this.advance());
    overlay.addEventListener('timeupdate', () => {
      if (this.session && this.chunk) {
        this.position = Math.min(this.chunk.end, this.chunk.start + overlay.currentTime);
        callbacks.position(this.position);
      }
    });
  }
  configure(job, duration) { this.stop(); this.job = job; this.duration = duration; }
  currentTime() { return this.session && this.chunk ? Math.min(this.chunk.end, this.chunk.start + this.overlay.currentTime) : this.position; }
  async begin(position, speed) {
    this.source.pause(); this.source.playbackRate = 1;
    this.position = position; this.speed = speed; this.chunk = null;
    const session = crypto.randomUUID(); this.session = session; this.pending = new Map();
    this.callbacks.state('buffering', 'Generating frames for this moment. Keep holding…');
    try {
      await this.request(`/api/live/${this.job}`, { session, active: true });
      if (session !== this.session) return;
      await this.playChunk(Math.floor(position / .5), position, session);
    } catch (error) { if (session === this.session) this.callbacks.error(error); }
  }
  async ensure(index, session) {
    if (session !== this.session) throw new Error('Hold released.');
    if (this.pending.has(index)) return this.pending.get(index);
    const job = this.job;
    const promise = (async () => {
      let chunk = await this.request(`/api/chunks/${job}`, { index, session });
      while (chunk.phase !== 'ready') {
        if (session !== this.session) throw new Error('Hold released.');
        if (['error', 'cancelled'].includes(chunk.phase)) throw new Error(chunk.message || 'Frame generation was cancelled.');
        await new Promise(resolve => setTimeout(resolve, 150));
        chunk = await this.request(`/api/chunks/${job}/${index}`);
      }
      return chunk;
    })();
    this.pending.set(index, promise);
    return promise;
  }
  async playChunk(index, position, session) {
    this.switching = true;
    this.callbacks.state('buffering', 'Generating AI frames for the next window…');
    const chunk = await this.ensure(index, session);
    if (session !== this.session) return;
    this.chunk = null; this.position = position;
    this.overlay.pause();
    this.overlay.src = chunk.url;
    await new Promise((resolve, reject) => {
      this.overlay.onloadedmetadata = resolve;
      this.overlay.onerror = () => reject(new Error('The browser could not play the AI window.'));
      this.overlay.load();
    });
    if (session !== this.session) return;
    this.overlay.currentTime = Math.min(Math.max(0, position - chunk.start), Math.max(0, this.overlay.duration - 1 / 120));
    this.overlay.playbackRate = this.speed; this.overlay.muted = this.source.muted;
    this.chunk = chunk; this.overlay.classList.add('loaded');
    await this.overlay.play();
    if (session !== this.session) { this.overlay.pause(); return; }
    this.switching = false;
    this.callbacks.state('playing', `AI slow motion. Window generated in ${chunk.seconds}s; next window is buffered ahead.`);
    if (chunk.end < this.duration - .001) {
      // At most one window ahead, and only while the hold session is active.
      this.ensure(index + 1, session).catch(() => {});
    }
  }
  async advance() {
    if (!this.session || this.switching || !this.chunk) return;
    const session = this.session;
    this.position = this.chunk.end;
    if (this.position >= this.duration - .001) { this.callbacks.end(); return; }
    try { await this.playChunk(this.chunk.index + 1, this.position, session); }
    catch (error) { if (session === this.session) this.callbacks.error(error); }
  }
  stop() {
    const position = this.currentTime(), session = this.session, job = this.job;
    this.session = null; this.chunk = null; this.switching = false;
    this.overlay.pause(); this.overlay.classList.remove('loaded');
    this.overlay.removeAttribute('src'); this.overlay.load();
    if (session) this.request(`/api/live/${job}`, { session, active: false }).catch(() => {});
    this.callbacks.state('idle', 'Ready. GPU interpolation starts on your next hold.');
    return position;
  }
}
