"""Application entry point."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from lucid_camera_control.ui.main_window import MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LUCID Camera Control")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Create and close the UI without entering the event loop.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("LUCID Camera Control")
    app.setOrganizationName("RocketWill")

    window = MainWindow()
    if args.smoke_test:
        window.show()
        app.processEvents()
        window.close()
        app.processEvents()
        return 0

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

