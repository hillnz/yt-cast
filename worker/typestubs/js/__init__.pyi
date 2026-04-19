"""Type stubs for the Pyodide ``js`` module.

The ``js`` module is injected by the Pyodide runtime and provides access to
JavaScript global objects.  These stubs cover the subset used by the
drive-proxy worker so that Pyright/Pylance can resolve imports.
"""

from collections.abc import Callable, Iterator

from pyodide.ffi import JsProxy as JsProxy

# ---------------------------------------------------------------------------
# Opaque types for JS concepts without direct Python equivalents
#
# These inherit from ``pyodide.ffi.JsProxy`` so that values returned by
# ``to_js()`` / ``create_proxy()`` are assignable to parameters typed as
# ``JsProxy`` without requiring explicit casts.
# ---------------------------------------------------------------------------

class JsObject(JsProxy):
    """A plain JavaScript object (e.g. the result of ``Object.fromEntries``)."""

class CryptoKey(JsProxy):
    """Opaque handle returned by ``SubtleCrypto.importKey``."""

class ArrayBuffer(JsProxy):
    """Opaque handle representing a JavaScript ``ArrayBuffer``."""

# ---------------------------------------------------------------------------
# console
# ---------------------------------------------------------------------------

class _Console:
    def log(self, *args: object) -> None: ...
    def error(self, *args: object) -> None: ...
    def warn(self, *args: object) -> None: ...
    def info(self, *args: object) -> None: ...
    def debug(self, *args: object) -> None: ...

console: _Console

# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

class _ReadableStream:
    locked: bool
    async def cancel(self, reason: JsProxy = ...) -> None: ...
    def getReader(self) -> JsProxy: ...
    def pipeThrough(self, transform: JsProxy) -> "_ReadableStream": ...
    def pipeTo(self, dest: JsProxy) -> JsProxy: ...
    def tee(self) -> JsProxy: ...

class JsResponse:
    ok: bool
    status: int
    statusText: str
    headers: "Headers"
    body: _ReadableStream

    @staticmethod
    def new(
        body: str | bytes | _ReadableStream | JsProxy | None = ...,
        init: JsProxy | None = ...,
    ) -> "JsResponse": ...
    async def text(self) -> str: ...
    async def json(self) -> JsProxy: ...
    async def arrayBuffer(self) -> ArrayBuffer: ...
    async def blob(self) -> JsProxy: ...

Response = JsResponse

async def fetch(input: str | "Request", init: JsProxy | None = ...) -> JsResponse: ...

# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------

class Headers:
    @staticmethod
    def new(init: JsProxy | None = ...) -> "Headers": ...
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...
    def append(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...
    def has(self, name: str) -> bool: ...
    def entries(self) -> JsProxy: ...
    def keys(self) -> JsProxy: ...
    def values(self) -> JsProxy: ...

# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class Request:
    url: str
    method: str
    headers: Headers
    body: _ReadableStream | None

    @staticmethod
    def new(input: str | "Request", init: JsProxy | None = ...) -> "Request": ...
    async def text(self) -> str: ...
    async def json(self) -> JsProxy: ...

# ---------------------------------------------------------------------------
# WebSocketPair
# ---------------------------------------------------------------------------

class WebSocket(JsProxy):
    def accept(self) -> None: ...
    def send(self, message: str | bytes) -> None: ...
    def close(self, code: int = ..., reason: str = ...) -> None: ...
    def addEventListener(
        self, event: str, listener: Callable[..., object] | JsProxy
    ) -> None: ...
    def removeEventListener(
        self, event: str, listener: Callable[..., object] | JsProxy
    ) -> None: ...

class _WebSocketPair:
    @staticmethod
    def new() -> "_WebSocketPair": ...
    def object_values(self) -> tuple[WebSocket, WebSocket]: ...

WebSocketPair = _WebSocketPair

# ---------------------------------------------------------------------------
# TextEncoder / Uint8Array
# ---------------------------------------------------------------------------

class TextEncoderInstance:
    def encode(self, input: str = ...) -> "Uint8Array": ...

class TextEncoder:
    @staticmethod
    def new() -> TextEncoderInstance: ...

class Uint8Array:
    buffer: ArrayBuffer
    length: int
    byteLength: int
    byteOffset: int

    @staticmethod
    def new(
        source: ArrayBuffer | "Uint8Array" | int | JsProxy = ...,
    ) -> "Uint8Array": ...
    def __bytes__(self) -> bytes: ...
    def __iter__(self) -> Iterator[int]: ...
    def __len__(self) -> int: ...

# ---------------------------------------------------------------------------
# crypto (Web Crypto API)
# ---------------------------------------------------------------------------

class _SubtleCrypto:
    async def importKey(
        self,
        format: str,
        keyData: JsProxy | ArrayBuffer,
        algorithm: str | JsProxy,
        extractable: bool,
        keyUsages: JsProxy,
    ) -> CryptoKey: ...
    async def sign(
        self,
        algorithm: str | JsProxy,
        key: CryptoKey,
        data: JsProxy | Uint8Array,
    ) -> ArrayBuffer: ...
    async def verify(
        self,
        algorithm: str | JsProxy,
        key: CryptoKey,
        signature: JsProxy | Uint8Array | ArrayBuffer,
        data: JsProxy | Uint8Array,
    ) -> bool: ...
    async def digest(
        self, algorithm: str | JsProxy, data: JsProxy | Uint8Array
    ) -> ArrayBuffer: ...
    async def encrypt(
        self,
        algorithm: str | JsProxy,
        key: CryptoKey,
        data: JsProxy | Uint8Array,
    ) -> ArrayBuffer: ...
    async def decrypt(
        self,
        algorithm: str | JsProxy,
        key: CryptoKey,
        data: JsProxy | Uint8Array,
    ) -> ArrayBuffer: ...

class _Crypto:
    subtle: _SubtleCrypto
    def getRandomValues(self, array: Uint8Array) -> Uint8Array: ...
    def randomUUID(self) -> str: ...

crypto: _Crypto

# ---------------------------------------------------------------------------
# Object
# ---------------------------------------------------------------------------

class Object:
    @staticmethod
    def fromEntries(iterable: JsProxy) -> JsObject: ...
    @staticmethod
    def keys(obj: JsProxy) -> JsProxy: ...
    @staticmethod
    def values(obj: JsProxy) -> JsProxy: ...
    @staticmethod
    def entries(obj: JsProxy) -> JsProxy: ...
    @staticmethod
    def assign(target: JsProxy, *sources: JsProxy) -> JsObject: ...

# ---------------------------------------------------------------------------
# Cloudflare Workers runtime types (used by the ``workers`` package)
# ---------------------------------------------------------------------------

class DurableObjectStorage(JsProxy):
    """Durable Object persistent storage API."""
    async def get(self, key: str) -> JsProxy: ...
    async def put(self, key: str, value: object) -> None: ...
    async def delete(self, key: str) -> bool: ...
    async def deleteAll(self) -> None: ...
    async def list(self) -> JsProxy: ...

class DurableObjectState(JsProxy):
    """State object passed to Durable Object constructors."""

    storage: DurableObjectStorage

    def getWebSockets(self, tag: str = ...) -> JsProxy: ...
    def acceptWebSocket(self, ws: WebSocket, tags: JsProxy = ...) -> None: ...
    def waitUntil(self, promise: JsProxy) -> None: ...

class Env(JsProxy):
    """Cloudflare Worker environment bindings (secrets, KV, R2, DO namespaces, etc.)."""

class ExecutionContext(JsProxy):
    """Execution context for a Worker invocation."""
    def waitUntil(self, promise: JsProxy) -> None: ...
    def passThroughOnException(self) -> None: ...
