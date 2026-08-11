"""Capability snapshots and verified GenICam node writes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from enum import StrEnum
from typing import Any, Protocol


class NodeMapLike(Protocol):
    def get_node(self, name: str) -> Any: ...


class NodeKind(StrEnum):
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ENUMERATION = "enumeration"
    STRING = "string"
    COMMAND = "command"
    OTHER = "other"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class NodeCapability:
    name: str
    kind: NodeKind
    available: bool
    readable: bool
    writable: bool
    value: object | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    increment: int | float | None = None
    choices: tuple[str, ...] = ()
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class NodeWriteResult:
    name: str
    requested: object
    applied: object
    adjusted: bool
    capability: NodeCapability


class NodeAccessError(RuntimeError):
    def __init__(
        self,
        node_name: str,
        message: str,
        capability: NodeCapability | None = None,
    ) -> None:
        super().__init__(f"{node_name}: {message}")
        self.node_name = node_name
        self.capability = capability


class NodeAccessor:
    """Translate Arena node objects into stable application-facing behavior."""

    def __init__(self, nodemap: NodeMapLike) -> None:
        self._nodemap = nodemap

    def snapshot(self, name: str) -> NodeCapability:
        try:
            node = self._nodemap.get_node(name)
        except (KeyError, TypeError, ValueError):
            return self._unavailable(name)
        if node is None:
            return self._unavailable(name)

        readable = self._safe_bool(node, "is_readable")
        writable = self._safe_bool(node, "is_writable")
        kind = self._kind(node)
        value = self._safe_attr(node, "value") if readable else None
        minimum = None
        maximum = None
        increment = None
        choices: tuple[str, ...] = ()
        unit = self._optional_text(self._safe_attr(node, "unit"))

        if kind in (NodeKind.INTEGER, NodeKind.FLOAT):
            minimum = self._numeric_or_none(self._safe_attr(node, "min"))
            maximum = self._numeric_or_none(self._safe_attr(node, "max"))
            increment = self._numeric_or_none(self._safe_attr(node, "inc"))
        elif kind is NodeKind.ENUMERATION:
            choices = self._readable_enum_choices(node)

        return NodeCapability(
            name=name,
            kind=kind,
            available=True,
            readable=readable,
            writable=writable,
            value=value,
            minimum=minimum,
            maximum=maximum,
            increment=increment,
            choices=choices,
            unit=unit,
        )

    def snapshot_many(self, names: tuple[str, ...] | list[str]) -> tuple[NodeCapability, ...]:
        return tuple(self.snapshot(name) for name in names)

    def write_numeric(self, name: str, requested: int | float) -> NodeWriteResult:
        capability, node = self._writable_node(
            name,
            expected=(NodeKind.INTEGER, NodeKind.FLOAT),
        )
        if isinstance(requested, bool) or not isinstance(requested, (int, float)):
            raise NodeAccessError(name, "numeric value required", capability)
        if capability.minimum is None or capability.maximum is None:
            raise NodeAccessError(name, "numeric range is unavailable", capability)

        aligned = self.align_numeric(
            requested,
            capability.minimum,
            capability.maximum,
            capability.increment,
            integer=capability.kind is NodeKind.INTEGER,
        )
        try:
            node.value = aligned
        except Exception as exc:
            raise NodeAccessError(
                name,
                self._write_message(requested, capability, exc),
                capability,
            ) from exc
        return self._readback(name, requested, aligned)

    def write_enumeration(self, name: str, requested: str) -> NodeWriteResult:
        capability, node = self._writable_node(name, expected=(NodeKind.ENUMERATION,))
        if requested not in capability.choices:
            raise NodeAccessError(
                name,
                f"{requested!r} is not one of {capability.choices}",
                capability,
            )
        try:
            node.value = requested
        except Exception as exc:
            raise NodeAccessError(name, str(exc) or type(exc).__name__, capability) from exc
        return self._readback(name, requested, requested)

    def write_boolean(self, name: str, requested: bool) -> NodeWriteResult:
        capability, node = self._writable_node(name, expected=(NodeKind.BOOLEAN,))
        if not isinstance(requested, bool):
            raise NodeAccessError(name, "boolean value required", capability)
        try:
            node.value = requested
        except Exception as exc:
            raise NodeAccessError(name, str(exc) or type(exc).__name__, capability) from exc
        return self._readback(name, requested, requested)

    def execute_command(self, name: str) -> None:
        capability, node = self._writable_node(name, expected=(NodeKind.COMMAND,))
        try:
            node.execute()
        except Exception as exc:
            raise NodeAccessError(
                name,
                str(exc) or type(exc).__name__,
                capability,
            ) from exc

    @staticmethod
    def align_numeric(
        requested: int | float,
        minimum: int | float,
        maximum: int | float,
        increment: int | float | None,
        *,
        integer: bool,
    ) -> int | float:
        low = Decimal(str(minimum))
        high = Decimal(str(maximum))
        value = min(max(Decimal(str(requested)), low), high)
        if increment is not None and Decimal(str(increment)) > 0:
            step = Decimal(str(increment))
            steps = ((value - low) / step).to_integral_value(rounding=ROUND_FLOOR)
            value = min(low + steps * step, high)
        return int(value) if integer else float(value)

    def _writable_node(
        self,
        name: str,
        *,
        expected: tuple[NodeKind, ...],
    ) -> tuple[NodeCapability, Any]:
        capability = self.snapshot(name)
        if not capability.available:
            raise NodeAccessError(name, "node is unavailable", capability)
        if capability.kind not in expected:
            raise NodeAccessError(
                name,
                f"expected {expected}, got {capability.kind}",
                capability,
            )
        if not capability.writable:
            raise NodeAccessError(name, "node is not writable", capability)
        try:
            return capability, self._nodemap.get_node(name)
        except (KeyError, TypeError, ValueError) as exc:
            raise NodeAccessError(name, "node became unavailable", capability) from exc

    def _readback(
        self,
        name: str,
        requested: object,
        written: object,
    ) -> NodeWriteResult:
        capability = self.snapshot(name)
        if not capability.available or not capability.readable:
            raise NodeAccessError(name, "cannot verify applied value", capability)
        return NodeWriteResult(
            name=name,
            requested=requested,
            applied=capability.value,
            adjusted=capability.value != requested,
            capability=capability,
        )

    @staticmethod
    def _kind(node: Any) -> NodeKind:
        interface_type = NodeAccessor._safe_attr(node, "interface_type")
        name = str(getattr(interface_type, "name", interface_type or "")).casefold()
        return {
            "integer": NodeKind.INTEGER,
            "float": NodeKind.FLOAT,
            "boolean": NodeKind.BOOLEAN,
            "enumeration": NodeKind.ENUMERATION,
            "string": NodeKind.STRING,
            "command": NodeKind.COMMAND,
        }.get(name, NodeKind.OTHER)

    @staticmethod
    def _readable_enum_choices(node: Any) -> tuple[str, ...]:
        try:
            entry_nodes = node.enumentry_nodes
            return tuple(
                name
                for name in node.enumentry_names
                if name in entry_nodes and bool(entry_nodes[name].is_readable)
            )
        except Exception:
            return ()

    @staticmethod
    def _safe_attr(node: Any, name: str) -> Any | None:
        try:
            return getattr(node, name)
        except Exception:
            return None

    @staticmethod
    def _safe_bool(node: Any, name: str) -> bool:
        return bool(NodeAccessor._safe_attr(node, name))

    @staticmethod
    def _numeric_or_none(value: Any) -> int | float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _unavailable(name: str) -> NodeCapability:
        return NodeCapability(
            name=name,
            kind=NodeKind.UNAVAILABLE,
            available=False,
            readable=False,
            writable=False,
        )

    @staticmethod
    def _write_message(
        requested: object,
        capability: NodeCapability,
        error: Exception,
    ) -> str:
        return (
            f"failed to write requested={requested!r}; "
            f"range=[{capability.minimum}, {capability.maximum}], "
            f"increment={capability.increment}: {error}"
        )
