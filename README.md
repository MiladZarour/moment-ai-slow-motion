# Moment

Double-click **Start Moment.cmd**, then use the page at **http://127.0.0.1:8766**. Keep using that address; opening `index.html` directly does not connect to the AI engine.

1. Choose or drop a video. There is no fixed duration or file-size cap; available disk space and processing time determine practical limits.
2. Playable videos open directly at their original resolution and frame rate. Only formats the browser cannot decode are converted; that fallback displays measured progress from FFmpeg timestamps. There is no AI generation in either path.
3. Press Play and hold the bottom-right circle, or hold **S**, for smooth ¼× or ½× playback. Release to return to normal speed. Holding from pause returns to pause on release.
4. Each hold marks a slow-motion section. **Right-click a section badge or tap its ⋯ button**, then choose **Save this section as MP4** to export only that slowed clip, with audio. You can also right-click the video while the playhead is inside a marked section. Click **Download section MP4** when rendering finishes. The menu also lets you remove a section.
5. **Save full video** is the separate option for the entire clip, with marked sections slowed down and remaining footage at normal speed. Later holds replace overlapping parts in the full edit. Audio is stretched with pitch preserved.

The app uses **RIFE v4.6** through **rife-ncnn-vulkan**. The browser checks whether it can decode the selected file. If it can, the app uses the original file directly: no full-video conversion or downscaling. Only incompatible formats get a 30 fps playback copy, with measured conversion progress. AI windows and exported edits fit within 1280?720. **No AI interpolation runs on upload or during normal playback.**

Each hold opens a GPU session and generates half-second source windows around the current playhead. Each window gets three intermediate frames per source interval and is encoded at 120 fps. Quarter-speed playback therefore supplies 30 frames per playback second. While holding, at most one additional window is generated ahead. Releasing cancels unfinished work; completed windows stay cached for subsequent holds and export. No further windows are scheduled after release. Saving uses those cached AI windows for slowed sections and the normal playback copy for other sections. Output is H.264 MP4 at 30 fps with optional pitch-preserving stretched AAC audio.

**This is on-demand generation, with buffering.** The first uncached window takes time to decode, interpolate, and encode. Playback pauses with an explicit generation message instead of pretending ordinary slow playback is AI interpolation. More buffering can occur if generation cannot keep up, especially at half speed or higher resolutions. This portable engine starts a process for each window; it does not match Samsung's tightly integrated, persistent live inference. On this PC a 640?360 half-second window took about 1.5 seconds end to end in testing. No zero-latency guarantee is made. HDR preservation is not implemented.

Everything runs locally, including all interface assets. Source copies, normal previews, cached AI windows, and saved edits remain in `data/`; temporary JPEG frames are removed after each window. Stop the server before deleting `data/` to remove working data. Loaded video metadata is saved locally so the last upload can reopen after an engine restart. Marked sections currently last for the page session.

Requirements: Windows, Python 3, FFmpeg/ffprobe on PATH, and a working Vulkan-capable GPU driver. Dependencies are already installed on this PC. `setup.ps1` can download the RIFE Windows package again if needed. No Python packages, CUDA toolkit, or PyTorch installation are required. **Stop Moment.cmd** stops an idle background server. Start the server visibly for troubleshooting with `python server.py`; press Ctrl+C to stop it.

Engine source and bundled license: https://github.com/nihui/rife-ncnn-vulkan (MIT). Windows binary/model package: release `20221029`, downloaded from the official project's GitHub releases. This is an independent implementation, not Samsung's model.

Validation: `python -m unittest discover -s tests` covers section timing, overlap resolution, and sub-frame boundary handling. GPU pipeline and browser tests use generated video fixtures; see `VALIDATION.md` for recorded results.
