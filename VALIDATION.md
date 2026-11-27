# Validation — 25 October 2026

## Current on-demand implementation

API version 6 fixes the RIFE CLI frame-count mapping (input_count/output_count), anchors all extraction to one source-frame grid with seek overlap, preserves 29 fps and fractional native rates, targets three source seconds of lookahead, and encodes entire slowed sections continuously. A deterministic 29 fps moving-bar fixture was checked across seven window joins and two GPU batches: original-frame anchor error stayed below 0.013 pixels in preview and 0.145 pixels after saved MP4 compression. Join motion fell within the ordinary subpixel warp/compression variation; no special boundary drift was present. The running production app passed upload, native-rate hold/release, and section-only save in Chromium with no page errors. Five unit tests pass, including 29 fps and 24000/1001 frame grids.

Continuous playback update (API version 5): live windows are now video-only fragmented MP4s appended to one MediaSource buffer. Four windows share a RIFE model load, and each is published while the rest of the batch is still processing. Live preview fits within 960×540; saving regenerates the requested slowed sections at up to 1280×720. Browser tests confirmed stable stream URLs across boundaries, correct source-time/audio-clock synchronization, release cancellation, original-file playback, and 720p clip-only output with distinct interpolated frames.

Sustained 720p fixture measurements on this PC: quarter-speed initial buffer 2.926s, then 0.0012s total waiting during 16 seconds of playback; half-speed initial buffer 3.192s, then 0.0264s total waiting during 9.5 seconds. An existing long source at a later seek position needed 3.663s initially, then 0.0281s waiting during a 12-second quarter-speed hold, with source audio clock within 0.04 source seconds. These are measured test cases, not general performance guarantees. Initial latency remains; this is not Samsung's persistent native inference implementation.

A 19-second half-speed hold exercised old-buffer eviction: playback advanced 9.487 source seconds, retained only frames from 5.500 seconds onward, and measured 0.0405 seconds total waiting. This verifies the buffer does not grow indefinitely during sustained holds.

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

## Range editor update - 27 November 2026

A Chromium end-to-end test uploaded a 3-second fixture with zero AI calls on load, selected 0.5-1.5 seconds without hold marks, generated a 4-second quarter-speed MP4 with audio, played the plain/AI comparison, and downloaded the clip. Hold preview still records a moment. Cancellation before final rendering restored the selection controls. Desktop and 390px mobile screenshots were inspected; no horizontal overflow or uncaught page errors occurred. A focused follow-up verified that paused comparison clocks align within 0.02 source seconds and that marked moments expand only when present. No backend API or model changes were made in this update.

## Side-by-side comparison and 8x update - 27 November 2026

The finished comparison now appears above the editor, with matching rendered-speed labels, shared play/pause, replay, seeking, audio, and fullscreen. Both cards remain side by side at 390px. Changed selection settings display a notice while the last result retains its original speed labels.

Real GPU and Chromium integration passed: a 0.5-second source selection at 8x produced a 4-second MP4 with 120 video frames and audio. Preview windows contained 120 frames at 240 fps for a 30 fps source. The first eight decoded saved frames had distinct hashes, confirming additional interpolation rather than repeated 4x frames. Shared playback used 0.125 speed for the plain source and normal playback for the rendered clip; a paused seek aligned within 0.02 source seconds. Download, replay, and mute passed. Rendering the same selection at 4x and switching back to 8x reused separate caches without additional AI calls. The 8x live MediaSource hold played and recorded a marked section. No uncaught page errors occurred. Desktop and mobile screenshots were inspected. Six unit tests pass, including mixed 8x/4x export timing. API version remains 6 with a new slowFactors capability advertisement; the launcher upgrades an idle older engine.
