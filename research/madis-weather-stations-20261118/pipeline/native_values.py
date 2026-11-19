"""Interpret the native clock, text, and QC fields of the NOAA source."""

import json
import math
from typing import Any

import numpy as np

from observation_schema import numeric

DATASET = "noaa-madis-public1-integrated-mesonet"
QC_STATUS = {
    "Z": "unchecked",
    "C": "passed_level_1",
    "S": "passed_levels_1_2",
    "V": "passed_levels_1_2_3",
    "K": "passed_levels_1_2_3_4",
    "k": "failed_level_4",
    "X": "failed_level_1",
    "Q": "failed_level_2_or_3",
    "G": "subjective_good",
    "B": "subjective_bad",
}
QC_FAILURE = {"k", "X", "Q", "B"}
QC_EXPLICIT_NONFAILURE = {"C", "S", "V", "K", "G"}


def _number(value: Any) -> float | None:
    if value is None or np.ma.is_masked(value) or isinstance(value, (bool, np.bool_)):
        return None
    return numeric(value)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, np.ndarray):
        if value.dtype.kind not in "SU":
            if np.ma.is_masked(value):
                return ""
            return (
                str(value.item()).strip()
                if value.shape == ()
                else "".join(_text(x) for x in value).strip()
            )
        try:
            return (
                np.ma.filled(value, b"\0")
                .tobytes()
                .split(b"\0", 1)[0]
                .decode("utf-8", errors="replace")
                .strip()
            )
        except (TypeError, ValueError):
            return "".join(_text(x) for x in value).strip()
    if np.ma.is_masked(value):
        return ""
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _json_safe(value: Any) -> Any:
    if value is None or np.ma.is_masked(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode("utf-8", errors="replace").rstrip("\0")
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(
        _json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _qc(
    raw_descriptor: Any, raw_applied: Any, raw_results: Any, raw_detail: Any
) -> tuple[str, bool | None, str]:
    descriptor = _text(raw_descriptor)
    applied = _number(raw_applied)
    results = _number(raw_results)
    detail = _text(raw_detail)
    status = QC_STATUS.get(descriptor, "unknown")
    if descriptor in QC_FAILURE or (results is not None and results > 0):
        known_failure: bool | None = True
        if status.startswith("passed") or status == "unknown":
            status = "failed_native_qc_result"
    elif descriptor in QC_EXPLICIT_NONFAILURE:
        known_failure = False
    else:
        # A missing/unchecked/unknown flag is not evidence of a QC pass.
        known_failure = None
    native = {
        "descriptor": descriptor or None,
        "applied": int(applied) if applied is not None and applied >= 0 else None,
        "results": int(results) if results is not None and results >= 0 else None,
        "detail": detail or None,
    }
    return status, known_failure, _json(native)


def _variable_metadata(variable: Any) -> dict[str, Any]:
    return {name: _json_safe(getattr(variable, name)) for name in variable.ncattrs()}
