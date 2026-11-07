# Continuous progress recording

The development machine records color video to **D:\Team18-Recordings** on
the 4 TB `Work Backup` drive. Each run gets a new timestamped directory. No old
recordings are overwritten or automatically deleted.

`tools/camera_recorder.py` is the sole owner of the Aurora SDK connection. It
reads NV12 frames through the binary pipe mode in `camera_capture.cpp`, sends
them to FFmpeg, and publishes fresh snapshots to the calibration tools. It does
not connect to or command the robot. `visual_heading.py` and
`record_wheel_trial.py` automatically use this shared feed when the local
`.camera-recorder.json` configuration exists, so calibration does not interrupt
the archive. A missing/stale shared feed fails the calibration capture instead
of opening a competing camera connection.

## Files and resource use

- H.264 MP4, 640 x 400 at nominal 10 fps, split near five-minute boundaries.
- Fragmented MP4 makes completed fragments recoverable if a run is interrupted.
- `frames.jsonl` records the camera and host timestamps for every archived frame;
  use these timestamps for measurements rather than assuming perfect video timing.
- `events.jsonl` records camera gaps/reconnections. The recorder retries failures;
  it cannot recover pictures taken while the camera was disconnected.
- `status.json`, `capture.log`, and `encoder.log` support troubleshooting.
- The encoder uses one CPU thread. The short static-scene test used roughly
  175 MB/hour when extrapolated; actual storage depends on scene motion.
- Recording stops with 5 GiB free and preserves existing files. It does not
  restart itself after a Windows reboot or continue through computer sleep.
- This archive contains color video, not audio or raw depth measurements.

FFmpeg is installed locally outside Git from the
[Gyan Windows build](https://www.gyan.dev/ffmpeg/builds/), with its published
SHA-256 verified. The vendor SDK, FFmpeg binaries and recordings are external
dependencies/data; all authored recording and control code is in this repo.

## Control

From the repository, using the Python environment with `requirements.txt`:

```powershell
python tools/camera_shared.py status
python tools/camera_shared.py snapshot --output ../roverc-tools/current-frame
python tools/decode_camera.py ../roverc-tools/current-frame
python tools/camera_shared.py stop
```

The local configuration contains a random token and is excluded from Git. The
snapshot service listens only on loopback and requires that token. Snapshots
older than 1.5 seconds are refused. Stopping the recorder finishes its current
video file and releases the camera; it does not move or stop the robot.

To start again, `tools/start_camera_recorder.ps1` takes the Python executable,
compiled `camera_capture.exe`, vendor DLL directory, FFmpeg executable, and an
existing recording directory. It launches a hidden background process.

```powershell
./tools/start_camera_recorder.ps1 -Python <python.exe> -CameraExe <camera_capture.exe> -DllDirectory <vendor-folder> -Ffmpeg <ffmpeg.exe> -OutputDirectory D:\Team18-Recordings
```

Validation on this machine: a finite test produced three decodable H.264 video
files across rotation boundaries; a frame was decoded and visually inspected.
The live background run served a snapshot and a 34-frame calibration recording
while the archive continued. The zero-speed trial reported stopped/disarmed;
the shared-camera pose measurement changed by less than one pixel/degree.
