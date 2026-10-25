# Moment

Double-click **Start Moment.cmd**, then use the page at **http://127.0.0.1:8765**. Keep using that address; opening `index.html` directly does not connect to the AI engine.

1. Choose or drop a video (up to 2 minutes and 1 GB).
2. Wait for **AI frames ready**. Source playback remains available while the GPU prepares it.
3. Press Play and hold the bottom-right circle, or hold **S**, for smooth ¼× or ½× playback. Release to return to normal speed. Holding from pause returns to pause on release.
4. Each hold marks a slow-motion section. Remove individual sections or clear them all. Later holds replace overlapping parts in the exported edit.
5. Press **Save MP4**, wait for rendering, then **Download MP4**. The saved video contains the entire clip, with marked sections slowed down and the remaining sections at normal speed. Audio is stretched with pitch preserved.

The app uses the **RIFE v4.6** neural frame-interpolation model through **rife-ncnn-vulkan**. It converts the source to 30 fps at up to 1280×720 (preserving aspect ratio, without enlarging smaller videos), generates a 4× stream, and encodes a 120 fps preview. At quarter speed, 120 fps supplies 30 frames per playback second. Export is H.264 MP4 at 30 fps with optional AAC audio. Portrait videos are fit inside the same 1280×720 bounds. HDR preservation is not implemented.

Unlike Samsung's device-specific live inference, this implementation **prepares the video first**. Hold/release is instant after preparation. Processing time depends on clip length, resolution, and GPU speed. Interpolation can produce artifacts around occlusions, cuts, and fast movement; it estimates motion rather than recovering genuine captured frames.

Everything runs locally. There are no remote model APIs or runtime font requests. Copies of source videos, previews, and saved edits remain in `data/`; temporary frame images are removed automatically after preparation. To remove saved working data, stop the server and delete the `data` folder. Reloading the page can recover a prepared job while the server is still running; marked sections currently last for the page session.

Requirements: Windows, Python 3, FFmpeg/ffprobe on PATH, and a working Vulkan-capable GPU driver. Dependencies are already installed on this PC. `setup.ps1` can download the RIFE Windows package again if needed. No Python packages, CUDA toolkit, or PyTorch installation are required. **Stop Moment.cmd** stops an idle background server. Start the server visibly for troubleshooting with `python server.py`; press Ctrl+C to stop it.

Engine source and bundled license: https://github.com/nihui/rife-ncnn-vulkan (MIT). Windows binary/model package: release `20221029`, downloaded from the official project's GitHub releases. This is an independent implementation, not Samsung's model.

Validation: `python -m unittest discover -s tests` covers section timing, overlap resolution, and sub-frame boundary handling. GPU pipeline and browser tests use generated video fixtures; see `VALIDATION.md` for recorded results.
