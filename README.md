# LUCID Camera Control

LUCID Camera Control is a standalone Windows desktop application for one
Arena-compatible LUCID camera at a time. It uses the LUCID Arena SDK through
Python and provides camera-side ROI, live preview, image controls, PNG capture,
Raw AVI recording, JSON configuration, and factory reset from an English UI.

The application was developed and tested with a `TRI032S-C` running firmware
`1.69.0.0`. Other Arena-compatible LUCID models are discovered through their
GenICam capabilities instead of a model-specific node list, but no second model
was physically available during final acceptance.

## Functions

- Discover Arena-compatible LUCID cameras and select one by serial number.
- Connect, close, and manually reconnect one camera.
- Apply `Width`, `Height`, `OffsetX`, and `OffsetY` on the camera. The acquired
  buffer already has the applied ROI dimensions.
- Use centered or manual ROI offsets with node range and increment correction.
- Preview Mono8 frames with measured receive FPS.
- Adjust preview-only contrast without changing screenshots or recordings.
- Control exposure, gain, acquisition frame rate, gamma, black level, automatic
  white balance, and 1x1 or 2x2 binning when the connected camera supports the
  required nodes.
- Save lossless PNG files from the latest owned acquisition frame.
- Record Raw BGR8 AVI through a bounded disk-writing queue.
- Import and export validated schema-v1 JSON configuration.
- Load the last application preferences on the next launch.
- Restore the camera's Default UserSet after explicit confirmation.
- Write rotating local logs for state changes, failures, media output, and queue
  drops.

## Environment requirements

This project has a fixed delivery constraint: Python commands must run through
the existing Conda environment named `e2`. The project does not create a new
environment, download the Arena SDK, or install missing packages automatically.

### Operating system and camera software

The following items must already be available on the client computer:

1. Windows with a working Conda installation.
2. A Conda environment named `e2` using Python 3.12.
3. LUCID Arena SDK, including the transport layer and camera drivers required by
   the connected camera.
4. The Arena Python package available as `arena_api` inside `e2`.
5. A LUCID camera that ArenaView can discover and open.

For a GigE camera, the camera and network adapter must already be configured so
that ArenaView can discover the device. ArenaView or another application should
not keep the camera open while LUCID Camera Control is connecting to it.

### Tested Python environment

The final acceptance environment used these versions:

| Component | Version |
| --- | --- |
| Python | 3.12.13 |
| arena-api | 2.8.2 |
| NumPy | 2.4.4 |
| OpenCV | 4.11.0.86 |
| Pydantic | 2.13.0 |
| PySide6 | 6.11.1 |

[`requirements.txt`](requirements.txt) lists the direct runtime dependency
subset already installed in `e2`. It is not a complete Conda lockfile. Packages
such as `pywin32`, `shiboken6`, and the PySide6 component packages are transitive
dependencies supplied by the existing environment.

If a listed package is missing or has a different version, treat the environment
as unverified. Do not upgrade, replace, or install packages into `e2` without
checking the effect on the other applications that share this environment.

## Setup

### 1. Clone the repository

```powershell
git clone https://github.com/RocketWill/lucid-camera-control.git
Set-Location lucid-camera-control
```

### 2. Confirm that `e2` exists

```powershell
conda env list
conda run -n e2 python --version
```

The Python version must satisfy the project range in `pyproject.toml`:
`>=3.12,<3.13`.

### 3. Check the required imports and versions

```powershell
conda run -n e2 python -c "import arena_api, cv2, numpy, pydantic, PySide6; print('Required imports: OK'); print('opencv:', cv2.__version__); print('numpy:', numpy.__version__); print('pydantic:', pydantic.__version__); print('PySide6:', PySide6.__version__)"
conda run -n e2 python -m pip show arena-api
conda run -n e2 python -m pip check
```

`arena_api` does not expose a reliable package version attribute in this tested
release. The `pip show arena-api` output is therefore the authoritative version
check for this dependency.

### 4. Confirm Arena camera discovery

Close ArenaView after its camera check, then run:

```powershell
conda run -n e2 python -c "from arena_api.system import system; print([(item.get('model'), item.get('ip')) for item in system.device_infos])"
```

An empty list means Arena did not discover a camera. Resolve the Arena SDK,
driver, transport, network, or camera power issue before starting the
application.

### 5. Register the local project in `e2`

```powershell
conda run -n e2 python -m pip install --no-build-isolation --no-deps -e .
```

`--no-deps` is intentional. It prevents the editable installation from changing
the shared environment or downloading a newer dependency.

## Run

Run the module without activating Conda:

```powershell
conda run -n e2 python -m lucid_camera_control
```

After the editable installation, the registered GUI command is also available:

```powershell
conda run -n e2 lucid-camera-control
```

## Basic operation

1. Select `Explore Cameras`.
2. Select the required serial number and press `Connect`.
3. Configure hardware ROI and camera controls while the camera is connected.
4. Press `Start Preview`.
5. Save a PNG or start a Raw AVI recording when frames are available.
6. Stop recording before changing settings that affect frame dimensions.
7. Stop preview and close the camera when acquisition is finished.

ROI changes and imported camera settings stop and restart preview when required.
The UI disables commands that are not valid in the current state.

If the camera disconnects during acquisition, the application finalizes active
media where possible, releases the device, and returns to `Disconnected`.
Reconnect remains a manual operator action.

## ROI behavior

ROI is applied through the camera's GenICam nodes:

- `Width`
- `Height`
- `OffsetX`
- `OffsetY`

The application reads each node's minimum, maximum, and increment before writing
it. A request that does not fit the legal increment is aligned and read back, so
the UI reports the dimensions and offsets that the camera actually accepted.

Hardware ROI and 2x2 binning are mutually exclusive. Return binning to 1x1
before enabling ROI.

## Preview, screenshots, and recording

Preview contrast affects only the displayed copy. PNG screenshots and AVI
frames use the owned Mono8 acquisition frame before preview processing.

Screenshots default to:

```text
%USERPROFILE%\Pictures\LUCID Camera Control
```

Recordings default to:

```text
%USERPROFILE%\Videos\LUCID Camera Control
```

The recording path uses Raw BGR8 AVI. Raw video requires substantial disk
throughput and storage. The approximate uncompressed payload rate is:

```text
width x height x 3 bytes x frames per second
```

The recorder requires at least 2 GiB of free space before opening a file. It
stops and finalizes the AVI when free space falls below 512 MiB. A bounded queue
holds up to 120 pending frames. When disk writing cannot keep up, the oldest
queued frame is discarded and the dropped-frame counter increases; acquisition
and preview continue.

Some general media players do not support Raw BGR8 AVI. The acceptance files
were reopened successfully through OpenCV.

## JSON configuration

The JSON file stores the preferred camera serial number, requested ROI, camera
controls, media directories, preview contrast, and window preferences.

Import has two separate stages:

1. Parse and validate the complete file without changing the camera.
2. Apply camera settings only after a camera is connected and the operator
   presses `Apply Imported Camera Settings`.

Unknown schema versions, extra fields, invalid ranges, and the ROI/2x2-binning
conflict are rejected before camera mutation.

Example schema-v1 file:

```json
{
  "schema_version": 1,
  "preferred_camera_serial": null,
  "roi": {
    "enabled": false,
    "width": 0,
    "height": 0,
    "centered": true,
    "offset_x": 0,
    "offset_y": 0
  },
  "controls": {
    "exposure_auto": true,
    "exposure_time": 1000.0,
    "gain_auto": false,
    "gain": 0.0,
    "frame_rate_enabled": false,
    "frame_rate": 30.0,
    "gamma_enabled": null,
    "gamma": null,
    "black_level": null,
    "white_balance_auto": null,
    "binning": 1
  },
  "screenshot_directory": "C:\\CameraOutput\\Screenshots",
  "recording_directory": "C:\\CameraOutput\\Recordings",
  "preview_contrast": 1.0,
  "window": {
    "width": 1100,
    "height": 720,
    "maximized": false
  }
}
```

The last known good configuration is stored at:

```text
%LOCALAPPDATA%\RocketWill\LUCID Camera Control\config.json
```

On startup, the application restores UI and media preferences. It does not
write the stored camera settings until the operator connects a camera and
explicitly applies them.

## Factory reset

`Factory Reset` loads `UserSetSelector=Default` through `UserSetLoad`. It does
not use `DeviceReset` and does not restart the physical device.

The command stops and finalizes recording, stops preview, loads the Default
UserSet, refreshes node capabilities, and remains connected when the camera
supports that sequence. Previous camera settings are not reapplied afterward.

Factory reset changes camera parameters immediately. Check exposure, gain,
frame rate, pixel format, ROI, and optional controls before starting the next
acquisition.

## Logs

Rotating logs are stored at:

```text
%LOCALAPPDATA%\RocketWill\LUCID Camera Control\logs\lucid-camera-control.log
```

Each file is limited to 2 MiB, with five backups retained. Logs include command
state, failures, recording paths, final frame counters, and recording queue
drops. Camera serial numbers may appear as device identity and should be removed
before sharing logs outside the intended support channel.

## Verification

Run all checks through `e2`:

```powershell
conda run -n e2 python -m unittest discover -s tests -v
conda run -n e2 python -m compileall -q src tests
conda run -n e2 python -m pip check
conda run -n e2 python -m lucid_camera_control --smoke-test
git diff --check
```

Final automated verification contains 69 tests. Hardware acceptance on the
TRI032S-C covered repeated connect and close, ROI alignment, centered 1920x1080
acquisition, PNG and Raw AVI dimensions, measured receive FPS, and Default
UserSet reset.

## Known limits

- One camera can be connected at a time.
- Acquisition is continuous. Software and hardware trigger modes are outside
  the current scope.
- Reconnect is manual.
- The application requires the Arena SDK and the existing `e2` environment.
- No standalone EXE is included.
- Final hardware acceptance used one TRI032S-C. A second LUCID model was not
  available for physical verification.
