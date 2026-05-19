# LUCID Camera Control

Standalone Python desktop application for controlling LUCID Vision Labs cameras.

The application is intended to support camera discovery and selection, hardware ROI, live preview, recording, screenshots, FPS monitoring, common image controls, JSON configuration import/export, and restoration of factory settings.

## Runtime constraint

The application must run with the existing `conda e2` environment. Production dependencies may not be added without explicit approval.

## Status

PRD and technical design are approved. Implementation is in progress.

## Development setup

LUCID Arena SDK and the `conda e2` environment must already be installed.

```powershell
conda run -n e2 python -m pip install --no-build-isolation --no-deps -e .
```

The editable install registers only this local project and does not download or upgrade dependencies.

## Run

```powershell
conda run -n e2 python -m lucid_camera_control
```

## Verify

```powershell
conda run -n e2 python -m unittest discover -s tests -v
conda run -n e2 python -m lucid_camera_control --smoke-test
```
