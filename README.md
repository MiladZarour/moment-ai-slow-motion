# Moment

Double-click **Start Moment.cmd**, then use the page at **http://127.0.0.1:8766**. Keep using that address; opening `index.html` directly does not connect to the AI engine.

1. Choose or drop a video. There is no fixed duration or file-size cap; available disk space and processing time determine practical limits.
2. Playable videos open directly at their original resolution and frame rate. Only formats the browser cannot decode are converted; that fallback displays measured progress from FFmpeg timestamps. There is no AI generation in either path.
3. Press Play and hold the bottom-right circle, or hold **S**, for smooth ¼× or ½× playback. Release to return to normal speed. Holding from pause returns to pause on release.
4. Each hold marks a slow-motion section. **Right-click a section badge or tap its ⋯ button**, then choose **Save this section as MP4** to export only that slowed clip, with audio. You can also right-click the video while the playhead is inside a marked section. Click **Download section MP4** when rendering finishes. The menu also lets you remove a section.
5. **Save full video** is the separate option for the entire clip, with marked sections slowed down and remaining footage at normal speed. Later holds replace overlapping parts in the full edit. Audio is stretched with pitch preserved.

The app uses **RIFE v4.6** through **rife-ncnn-vulkan**. The browser checks whether it can decode the selected file. If it can, the app uses the original file directly: no full-video conversion or downscaling. Only incompatible formats get a 30 fps playback copy, with measured conversion progress. AI windows and exported edits fit within 1280?720. **No AI interpolation runs on upload or during normal playback.**

Each hold opens a GPU session at the current playhead. RIFE processes up to four half-second windows per model load and publishes completed windows while continuing to generate the rest. The browser appends them to one continuous MediaSource stream, rather than reloading a video at every boundary. A short initial buffer helps the GPU stay ahead. The stream's buffer is bounded and old frames are discarded during long holds. Releasing cancels unfinished work; completed windows remain cached.

Live AI preview fits within **960?540** for smoother playback. **Saving renders the selected slow-motion intervals again at up to 1280?720**; normal portions use the original video. Saved clips are H.264 MP4 at 30 fps, with optional pitch-preserving stretched AAC audio. No full-video AI generation runs on upload.

The normal source video supplies the live audio clock while the silent AI stream supplies the picture. Playback and audio pause together if the GPU buffer runs dry. Tested in Chromium/Edge-compatible MediaSource playback. Current Chrome or Edge is required for the smooth AI player.

**There is still an initial buffer, rather than Samsung-like zero-latency inference.** On this PC, uncached 720p source tests needed approximately 3?3.7 seconds before continuous playback started. In sustained tests, subsequent waiting totaled around 1?28 milliseconds. These measurements are not a guarantee for every video, codec, GPU load, or source position. Saving high-quality sections takes additional GPU time. HDR preservation is not implemented.

Everything runs locally, including all interface assets. Source copies, normal previews, cached AI windows, and saved edits remain in `data/`; temporary JPEG frames are removed after each window. Stop the server before deleting `data/` to remove working data. Loaded video metadata is saved locally so the last upload can reopen after an engine restart. Marked sections currently last for the page session.

Requirements: Windows, Python 3, FFmpeg/ffprobe on PATH, and a working Vulkan-capable GPU driver. Dependencies are already installed on this PC. `setup.ps1` can download the RIFE Windows package again if needed. No Python packages, CUDA toolkit, or PyTorch installation are required. **Stop Moment.cmd** stops an idle background server. Start the server visibly for troubleshooting with `python server.py`; press Ctrl+C to stop it.

Engine source and bundled license: https://github.com/nihui/rife-ncnn-vulkan (MIT). Windows binary/model package: release `20221029`, downloaded from the official project's GitHub releases. This is an independent implementation, not Samsung's model.

Validation: `python -m unittest discover -s tests` covers section timing, overlap resolution, and sub-frame boundary handling. GPU pipeline and browser tests use generated video fixtures; see `VALIDATION.md` for recorded results.
