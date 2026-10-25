# Validation — 25 October 2026

## Current on-demand implementation

Direct playback update (API version 4): compatible input was decoded by the browser and used as the original source, with no `preview.mp4` conversion file created. On-demand AI windows and section-only export passed against that original-file path, including audio duration checks. A previously uploaded long 1080p file reopened after engine restart and decoded at its original dimensions. The superseded full-video conversion was stopped. Incompatible-format fallback reports `out_time_us` from FFmpeg instead of a fixed percentage; its `convertedSeconds` field was verified after a real conversion. Ready-job metadata now persists across restarts.

Upload recovery: the production listener was still an older process and logged HTTP 413 for an upload over its old 1 GB limit. The launcher now checks API version 3 and restarts an idle outdated engine. The active listener was upgraded and reports no duration/file-size cap, plus section export support. A real Chromium file upload reached ready with zero AI calls. A simulated stale health response was rejected before any upload request was sent.

Section-only export: tested two marked sections, right-clicked the first, exported only its selected time range, and checked video/audio durations against the quantized interval divided by playback speed. The exported file has a `moment-section-` name. Escape dismissal, mobile ⋯ menu positioning, and removal were tested in Chromium. Section export is rejected by the client when an older server does not advertise support, preventing an accidental full-video export before restart.

The earlier full-video interpolation implementation described below has been replaced. Current checks passed:

- Upload and ordinary playback leave `aiInvocations` at zero and create no AI windows.
- Holding starts GPU interpolation at the playhead; each half-second window uses a real next-frame endpoint and produces a 120 fps clip. Only the next window is prefetched, while the hold remains active.
- Chromium keyboard hold crossed multiple generated windows. Release restored the source position, returned to pause when appropriate, hid the AI player, and cancelled unfinished generation. No new inference calls were started after release.
- Releasing before any AI window became ready produced no marked section and left no stale AI overlay or buffering indicator.
- Cached half-speed playback was tested with a mouse hold; releasing outside the button restored normal playback and recorded the section correctly.
- The marked interval exported and downloaded successfully as an MP4 with audio.
- Silent portrait integration passed: no AI on upload; two explicitly requested half-second AI windows; 60 frames per window at 120 fps; distinct decoded frames on moving content; overlapping quarter-/half-speed sections exported at the expected 2.2-second duration; HTTP range seeking succeeded.
- Desktop screenshots were inspected and mobile-width layout checked for overflow. Physical touch hardware remains untested.
- Half-second windows at 640×360 took approximately 1.5 seconds each including extraction, RIFE process startup, inference, and encoding. There is a visible first-window buffer and potential further buffering when the GPU pipeline cannot keep up.

Current application address: **http://127.0.0.1:8766**. Start/stop launchers use this port. No cloud inference is used.

## Earlier full-video prototype (historical results)

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
