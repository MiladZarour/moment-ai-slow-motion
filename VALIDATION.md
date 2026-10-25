# Validation — 25 October 2026

Environment: Windows, NVIDIA GeForce RTX 3060 Ti (8 GB), Python 3.15, FFmpeg, official RIFE ncnn Vulkan Windows release 20221029, RIFE v4.6 model.

Passed:

- Python compilation and JavaScript syntax checks.
- Three unit tests covering edit timing, later-hold overlap precedence, sub-frame gaps, invalid speeds, and non-finite times.
- Real GPU inference: 3-second 640×360 moving test pattern with audio, 90 source frames → 360 output frames; prepared video verified as 120 fps.
- Initial 720p inference measurement: 7.51 seconds for 360 output frames (47.9 frames/s). After preventing unnecessary upscaling, the 640×360 fixture took 2.26 seconds for 360 frames (159.4 frames/s). These are inference-only measurements, not total load time or general performance guarantees.
- Real Chromium browser: local video selection, preparation progress, mouse hold at quarter speed, release restoring normal speed and paused state, keyboard hold at half speed, section creation, MP4 render, download, and clear sections.
- Browser layout checked at 1365 px and 390 px widths, with screenshots inspected and no horizontal overflow. No uncaught JavaScript errors in the tested flow. Physical touch hardware was not tested.
- Audio export: 3-second source with a 1-second quarter-speed section and a .5-second half-speed section produced 6.5 seconds of H.264 video at 30 fps, plus 6.521 seconds of AAC audio (encoder padding).
- Silent portrait: 180×320 source preserved its dimensions, 30 frames → 120 frames. First eight decoded frames had distinct hashes on a moving test pattern. Overlapping quarter-/half-speed edits exported a 2.2-second silent MP4 as expected.
- HTTP byte-range seeking returned 206 with the requested byte count.
- Idle server shutdown endpoint and Windows launcher startup were exercised.

Local browser test script and screenshots are in `tools/` (ignored generated development assets). Unit tests are in `tests/test_edits.py`. `python tests/pipeline_smoke.py` runs the silent portrait integration check against an already running server.

Downloaded release archive SHA-256:

`D8E4D772D26CD8006EF0AD0BC82EB191B53C68677D1AE2F42506D74CBBBEA606`

Limitations: full-video preparation is required before AI hold playback. Output is limited to 720p bounds and 30 fps export; inputs are normalized to 30 fps before 4× interpolation. HDR preservation and Samsung's proprietary live inference are not implemented. Quality on arbitrary real-world footage has not been benchmarked.
