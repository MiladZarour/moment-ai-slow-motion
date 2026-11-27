# Moment

Double-click **Start Moment.cmd**, then use the page at **http://127.0.0.1:8766**. Keep using that address; opening `index.html` directly does not connect to the AI engine.

1. Choose or drop a video. There is no fixed duration or file-size cap; disk space and processing time determine practical limits.
2. In **Pick your moment**, enter start/end times in seconds, drag the range handles, or scrub the player and choose **Use playhead**.
3. Choose **2x**, **4x**, or **8x** slower and click **Create slow-motion clip**. Only the selected range is requested. Frame generation can be cancelled before final rendering begins.
4. The result appears above the editor: **Plain slowdown** beside **AI slow motion**, both at the rendered speed. **Play both**, replay, the shared timeline, audio, and fullscreen control the comparison together. **Download AI clip** saves only the selected moment as MP4, including audio when present. Changing settings keeps the last result accurately labeled until a new clip is created.
5. For a quick live preview, hold the corner control or **S**. Releasing marks a moment under **Moments marked with Hold**. Right-click a marked moment or use its menu to save it. **Save full edit** remains available for the complete video with marked speed changes.

Compatible videos play directly at original quality. Only incompatible formats require conversion, with measured progress. Nothing is sent to a cloud service. **Start Moment.cmd** upgrades an idle older engine so that 8x generation is available.


The app uses **RIFE v4.6** through **rife-ncnn-vulkan**. The browser checks whether it can decode the selected file. If it can, the app uses the original file directly: no full-video conversion or downscaling. Only incompatible formats get a 30 fps playback copy, with measured conversion progress. AI windows and exported edits fit within 1280?720. **No AI interpolation runs on upload or during normal playback.**

Each hold opens a GPU session at the current playhead. RIFE processes up to six frame-aligned windows per model load and publishes completed windows while continuing to generate the rest. The browser appends them to one continuous MediaSource stream, rather than reloading a video at every boundary. A short initial buffer helps the GPU stay ahead. The stream's buffer is bounded and old frames are discarded during long holds. Releasing cancels unfinished work; completed windows remain cached.

Live AI preview fits within **960?540** for smoother playback. **Saving renders the selected slow-motion intervals again at up to 1280?720**; the source frame rate (up to 30 fps) is preserved. Normal portions use the original video. Saved clips are H.264 MP4 at the preserved source frame rate, with optional pitch-preserving stretched AAC audio. No full-video AI generation runs on upload.

The normal source video supplies the live audio clock while the silent AI stream supplies the picture. Playback and audio pause together if the GPU buffer runs dry. Tested in Chromium/Edge-compatible MediaSource playback. Current Chrome or Edge is required for the smooth AI player.

**There is still an initial buffer, rather than Samsung-like zero-latency inference.** On this PC, uncached 720p source tests needed approximately 3?3.7 seconds before continuous playback started. In sustained tests, subsequent waiting totaled around 1?28 milliseconds. These measurements are not a guarantee for every video, codec, GPU load, or source position. Saving high-quality sections takes additional GPU time. HDR preservation is not implemented.

Everything runs locally, including all interface assets. Source copies, normal previews, cached AI windows, and saved edits remain in `data/`; temporary JPEG frames are removed after each window. Stop the server before deleting `data/` to remove working data. Loaded video metadata is saved locally so the last upload can reopen after an engine restart. Marked sections currently last for the page session.

Requirements: Windows, Python 3, FFmpeg/ffprobe on PATH, and a working Vulkan-capable GPU driver. Dependencies are already installed on this PC. `setup.ps1` can download the RIFE Windows package again if needed. No Python packages, CUDA toolkit, or PyTorch installation are required. **Stop Moment.cmd** stops an idle background server. Start the server visibly for troubleshooting with `python server.py`; press Ctrl+C to stop it.

Engine source and bundled license: https://github.com/nihui/rife-ncnn-vulkan (MIT). Windows binary/model package: release `20221029`, downloaded from the official project's GitHub releases. This is an independent implementation, not Samsung's model.

Validation: `python -m unittest discover -s tests` covers section timing, overlap resolution, and sub-frame boundary handling. GPU pipeline and browser tests use generated video fixtures; see `VALIDATION.md` for recorded results.

Frame continuity: source frames are sampled on one global frame grid with decode overlap. Window boundaries use 15 source frames, rather than assuming every video is 30 fps. RIFE receives exactly four outputs per input frame for 2x/4x modes and eight for 8x mode; context/end padding is trimmed. The 8x mode generates additional AI frames rather than stretching a 4x render. Preview and export caches are separate for the two interpolation factors. Each saved slow-motion section is encoded continuously. The player targets roughly three source seconds of lookahead while held. Higher interpolation factors require more GPU work.
