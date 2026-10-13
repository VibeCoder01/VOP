"""Browser sessions share API authorization; writes require session CSRF and same origin."""
import hmac
import sqlite3
from threading import Lock
from urllib.parse import parse_qs, urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse


class BrowserAuth:
    def __init__(self, app, *, token, store, pipeline, viewer_token=None):
        self.app, self.token, self.store, self.pipeline = app, token.encode("ascii"), store, pipeline
        self.viewer = viewer_token.encode("ascii") if viewer_token else None
        self.admission = Lock()

    def credential_role(self, supplied: bytes):
        if hmac.compare_digest(supplied, self.token):
            return "operator"
        if self.viewer and hmac.compare_digest(supplied, self.viewer):
            return "viewer"
        return None

    async def audit_denial(self, action):
        try:
            await run_in_threadpool(self.store.audit, action, "denied")
        except sqlite3.Error:
            pass

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        path, method = scope["path"], scope["method"]
        host = headers.get(b"host", b"").decode("ascii", "ignore")
        if host.split(":")[0] not in ("127.0.0.1", "localhost", "testserver"):
            return await JSONResponse({"error": "host_denied"}, status_code=400)(scope, receive, send)
        session = scope.get("session", {})
        bearer = b"authorization" in headers
        supplied = headers.get(b"authorization", b"")
        role = self.credential_role(supplied[7:]) if bearer and supplied.startswith(b"Bearer ") else (None if bearer else session.get("role"))
        public = path in ("/login", "/ui/style.css", "/favicon.ico")
        wants_html = b"text/html" in headers.get(b"accept", b"")
        if not role and not public:
            await self.audit_denial("authentication")
            response = RedirectResponse("/login", status_code=303) if wants_html and not path.startswith("/api/") else JSONResponse({"error": "authentication_required"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
            return await response(scope, receive, send)
        scope["auth_role"] = role
        origin = headers.get(b"origin")
        expected_origin = f"{scope.get('scheme', 'http')}://{host}".encode()
        if origin and (bearer or origin != expected_origin):
            await self.audit_denial("browser_origin")
            return await JSONResponse({"error": "browser_origin_denied"}, status_code=403)(scope, receive, send)
        if method not in ("GET", "HEAD", "OPTIONS"):
            if role == "viewer" and path != "/logout":
                await self.audit_denial("permission")
                return await JSONResponse({"error": "operator_required"}, status_code=403)(scope, receive, send)
            if not bearer:
                # Native URL-encoded forms only: bounded bodies, no arbitrary multipart parsing.
                body = bytearray()
                request = Request(scope, receive)
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 65536:
                        return await JSONResponse({"error": "form_too_large"}, status_code=413)(scope, receive, send)
                    body.extend(chunk)
                try:
                    form = parse_qs(bytes(body).decode("utf-8"), keep_blank_values=True)
                    csrf = form.get("csrf", [""])[0]
                    expected_csrf = session.get("csrf", "")
                    valid_csrf = bool(expected_csrf) and hmac.compare_digest(csrf.encode(), expected_csrf.encode())
                except (UnicodeError, ValueError):
                    valid_csrf = False
                if not valid_csrf:
                    await self.audit_denial("csrf")
                    return await JSONResponse({"error": "csrf_failed"}, status_code=403)(scope, receive, send)
                delivered = False
                async def replay_receive():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return {"type": "http.disconnect"}
                receive = replay_receive
        async def secured_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (b"cache-control", b"no-store"),
                                      (b"x-content-type-options", b"nosniff"),
                                      (b"content-security-policy", b"default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")]
            await send(message)
        admitted = method == "POST"
        if admitted and not self.admission.acquire(blocking=False):
            self.pipeline.skipped += 1
            await run_in_threadpool(self.store.audit, "capture_skipped", "overload")
            return await JSONResponse({"error": "overloaded"}, status_code=429)(scope, receive, secured_send)
        try:
            await self.app(scope, receive, secured_send)
        finally:
            if admitted:
                self.admission.release()
