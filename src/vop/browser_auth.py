"""Browser sessions share API authorization; writes require session CSRF and same origin."""
import hmac
from collections import deque
import sqlite3
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse


def configuring(request):
    """UI mode is per browser session; API credentials keep their existing role."""
    return request.scope.get('auth_role') == 'operator' and (
        request.headers.get('authorization', '').startswith('Bearer ') or
        request.scope.get('session', {}).get('mode', 'view') == 'configure')


class BrowserAuth:
    def __init__(self, app, *, token, store, pipeline, viewer_token=None):
        self.app, self.token, self.store, self.pipeline = app, token.encode("ascii"), store, pipeline
        self.viewer = viewer_token.encode("ascii") if viewer_token else None
        self.admission = Lock()
        self.login_attempts = deque()
        self.login_lock = Lock()

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
        public = path in ("/login", "/ui/style.css", "/favicon.ico") or path.startswith('/launch/') and method == 'GET'
        wants_html = b"text/html" in headers.get(b"accept", b"")
        if not role and not public:
            await self.audit_denial("authentication")
            response = RedirectResponse("/login", status_code=303) if wants_html and not path.startswith("/api/") else JSONResponse({"error": "authentication_required"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
            return await response(scope, receive, send)
        scope["auth_role"] = role
        # Keep observation and evidence reads available in View mode. Configuration,
        # deletion and lifecycle operations require an explicit browser mode switch.
        read_page = (path in ('/', '/observations', '/configure') or
                     path.startswith(('/ui/observations/', '/ui/evidence/', '/ui/preview/', '/ui/live-preview/')) and not path.endswith('/delete') or
                     path in ('/ui/workspace.js', '/ui/trends-refresh.js', '/ui/restart.js', '/ui/question-editor.js', '/ui/observe-images.js') or path.startswith('/api/'))
        if path == '/' and Request(scope).query_params.get('view', 'overview') in ('sources', 'questions', 'settings'):
            read_page = False
        preview_control = path.startswith('/ui/live-preview/') and path.endswith('/keepalive')
        view_action = path in ('/login', '/logout', '/ui/mode') or path.startswith('/ui/sources/') and path.endswith(('/capture', '/monitor')) or preview_control
        needs_configure = not public and not bearer and role == 'operator' and session.get('mode', 'view') != 'configure' and (
            not read_page if method in ('GET', 'HEAD') else not view_action)
        origin = headers.get(b"origin")
        expected_origin = f"{scope.get('scheme', 'http')}://{host}".encode()
        if origin and (bearer or origin != expected_origin):
            await self.audit_denial("browser_origin")
            return await JSONResponse({"error": "browser_origin_denied"}, status_code=403)(scope, receive, send)
        if method not in ("GET", "HEAD", "OPTIONS"):
            if path == "/login":
                now = monotonic()
                with self.login_lock:
                    while self.login_attempts and self.login_attempts[0] < now - 60:
                        self.login_attempts.popleft()
                    if len(self.login_attempts) >= 20:
                        return await JSONResponse({"error": "login_rate_limited"}, status_code=429, headers={"Retry-After": "60"})(scope, receive, send)
                    self.login_attempts.append(now)
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
                                      (b"content-security-policy", b"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")]
            await send(message)
        if needs_configure:
            response = RedirectResponse('/configure' if method in ('GET', 'HEAD') else '/configure?stale=1', status_code=303) if method in ('GET', 'HEAD') or wants_html else JSONResponse(
                {'error': 'configure_mode_required', 'message': 'Switch to Configure mode to change this workspace.', 'remediation': '/configure'}, status_code=403)
            return await response(scope, receive, secured_send)
        monitoring_control = path.startswith('/ui/sources/') and path.endswith('/monitor')
        scheduled_capture = path.startswith('/ui/sources/') and path.endswith('/capture')
        camera_test = path.startswith('/integration/cameras/') and path.endswith('/test')
        admitted = method == "POST" and not monitoring_control and not camera_test and not preview_control and path not in ('/api/v1/browser-ticket', '/api/v1/shutdown', '/ui/restart', '/ui/mode')
        acquired = admitted and self.admission.acquire(blocking=False)
        if admitted and not acquired and scheduled_capture:
            scope['capture_schedule_only'] = True
        elif admitted and not acquired:
            self.pipeline.skipped += 1
            await run_in_threadpool(self.store.audit, "capture_skipped", "overload")
            return await JSONResponse({"error": "overloaded"}, status_code=429)(scope, receive, secured_send)
        try:
            await self.app(scope, receive, secured_send)
        finally:
            if acquired:
                self.admission.release()
