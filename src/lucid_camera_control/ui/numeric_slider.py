"""Linked slider and precise numeric editor for a camera capability."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from lucid_camera_control.camera.nodes import NodeCapability


class NumericSliderControl(QWidget):
    def __init__(self, object_prefix: str, accessible_name: str) -> None:
        super().__init__()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName(f"{object_prefix}Slider")
        self.slider.setAccessibleName(f"{accessible_name} slider")
        self.spin_box = QDoubleSpinBox()
        self.spin_box.setObjectName(f"{object_prefix}SpinBox")
        self.spin_box.setAccessibleName(f"{accessible_name} value")
        self.spin_box.setDecimals(3)
        self.spin_box.setMinimumWidth(110)
        self.spin_box.setMaximumWidth(180)
        self.range_label = QLabel("Range unavailable")
        self.range_label.setObjectName(f"{object_prefix}RangeLabel")
        self.range_label.setAccessibleName(f"{accessible_name} range")
        self.range_label.setWordWrap(True)
        self.range_label.setMinimumWidth(0)
        self.range_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.addWidget(self.slider, stretch=1)
        value_row.addWidget(self.spin_box)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(value_row)
        layout.addWidget(self.range_label)

        self._minimum = 0.0
        self._step = 1.0
        self.slider.valueChanged.connect(self._slider_changed)
        self.spin_box.valueChanged.connect(self._spin_changed)

    def configure(self, capability: NodeCapability, fallback_step: float) -> None:
        minimum = float(capability.minimum or 0.0)
        maximum = float(capability.maximum or minimum)
        step = float(capability.increment or fallback_step)
        if step <= 0:
            step = fallback_step
        step = max(step, math.ulp(minimum) if minimum else math.ulp(1.0))
        positions = max(0, math.floor((maximum - minimum) / step))

        self._minimum = minimum
        self._step = step
        self.spin_box.setRange(minimum, maximum)
        self.spin_box.setSingleStep(step)
        if capability.unit:
            self.spin_box.setSuffix(f" {capability.unit}")
        else:
            self.spin_box.setSuffix("")
        self.slider.setRange(0, positions)
        if isinstance(capability.value, (int, float)) and not isinstance(
            capability.value, bool
        ):
            self.spin_box.setValue(float(capability.value))
        unit = f" {capability.unit}" if capability.unit else ""
        self.range_label.setText(
            f"Range: {minimum:g} to {maximum:g}{unit} | Step: {step:g}{unit}"
        )

    def _slider_changed(self, position: int) -> None:
        with QSignalBlocker(self.spin_box):
            self.spin_box.setValue(self._minimum + position * self._step)

    def _spin_changed(self, value: float) -> None:
        position = round((value - self._minimum) / self._step)
        with QSignalBlocker(self.slider):
            self.slider.setValue(position)
