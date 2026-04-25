"""FFI helpers for Python Workers."""

from js import Object
from pyodide.ffi import JsProxy
from pyodide.ffi import to_js as _to_js


def to_js(obj: object) -> JsProxy:
    """Convert a Python object to a JavaScript object.

    Uses ``Object.fromEntries`` so that Python dicts become plain JS objects
    (rather than ``Map`` instances which most Workers APIs won't accept).
    """
    return _to_js(obj, dict_converter=Object.fromEntries)
