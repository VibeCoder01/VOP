"""Authenticated loopback RPC for a local worker or an explicitly configured SSH tunnel."""
from datetime import timedelta
import json
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

from vop.contracts import AnswerKind, ProviderError, Status, utcnow
from vop.inputs.sources import NoRedirect
from vop.secrets import SecretStore, reference
from vop.worker_protocol import MAX_BODY, MAX_RESPONSE, decode_result, encode, request_body
from vop.measurements import utc


def profile(raw):
    from vop.config import identifier
    if not isinstance(raw, dict) or set(raw) - {"kind", "id", "version", "worker_id", "url", "secret_ref", "transport", "synthetic"} or raw.get("kind") != "worker":
        raise ValueError("Invalid worker profile")
    for key in ("id", "version", "worker_id"):
        identifier(raw.get(key))
    reference(raw.get("secret_ref"))
    parsed = urlsplit(raw.get("url", ""))
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username is not None or parsed.password is not None or parsed.path not in ("", "/") or parsed.query or parsed.fragment or not parsed.port or raw.get("transport") not in ("ssh", "local") or type(raw.get("synthetic", False)) is not bool:
        raise ValueError("Worker URL requires literal loopback HTTP and explicit local/SSH transport")
    return {**raw, "url": raw["url"].rstrip("/"), "synthetic": raw.get("synthetic", False)}


class RemoteInferenceEngine:
    def __init__(self, config, *, allow_remote=False, secrets=None, opener=None):
        self.config = profile(config)
        self.engine_id, self.engine_version = config["id"], config["version"]
        self.synthetic = self.config["synthetic"]
        self.allow_remote = allow_remote
        self.secrets = secrets or SecretStore()
        self.opener = opener or build_opener(NoRedirect(), ProxyHandler({}))
        self.last_health = None

    def capabilities(self):
        return tuple(AnswerKind)

    def _call(self, route, body=None, timeout=3):
        secret = self.secrets.get(self.config["secret_ref"])
        if not 32 <= len(secret) <= 256 or not secret.isascii() or any(c.isspace() for c in secret):
            raise ProviderError("secret_unavailable", "Worker secret has invalid format")
        data = encode(body) if body is not None else None
        if data and len(data) > MAX_BODY:
            raise ProviderError("request_too_large", "Worker request exceeds its byte limit")
        try:
            with self.opener.open(Request(self.config["url"] + route, data=data, headers={"Authorization": "Bearer " + secret, "Content-Type": "application/json"}), timeout=timeout) as response:
                payload = response.read(MAX_RESPONSE + 1)
            if len(payload) > MAX_RESPONSE:
                raise ValueError()
            return json.loads(payload, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except HTTPError as exc:
            self.last_health = None
            raise ProviderError("worker_auth" if exc.code in (401, 403) else "overloaded" if exc.code == 429 else "worker_rejected", "Worker refused the request") from None
        except (TimeoutError, OSError):
            self.last_health = None
            raise ProviderError("worker_unavailable", "Worker connection failed", Status.TIMEOUT) from None
        except ValueError:
            raise ProviderError("worker_protocol", "Worker returned invalid JSON") from None

    def health(self):
        try:
            value = self._call("/health")
            if (value.get("protocol"), value.get("worker_id"), value.get("engine_id"), value.get("engine_version"), value.get("synthetic")) != (1, self.config["worker_id"], self.engine_id, self.engine_version, self.synthetic):
                raise ValueError()
            if type(value.get("ready")) is not bool or type(value.get("synthetic")) is not bool or not isinstance(value.get("capabilities"), list) or any(k not in tuple(AnswerKind) for k in value["capabilities"]):
                raise ValueError()
            if abs((utc(value["utc"]) - utcnow()).total_seconds()) > 5:
                raise ProviderError("clock_skew", "Worker clock differs by more than five seconds")
            self.last_health = value
            return value
        except (ValueError, KeyError, AttributeError):
            raise ProviderError("worker_identity", "Worker identity or model does not match configured profile") from None

    def infer(self, request):
        if not self.allow_remote:
            raise ProviderError("remote_consent_required", "Confirm remote inference before sending image bytes")
        from vop.inputs.sources import MAX_IMAGE_BYTES
        if len(request.frame.payload) > MAX_IMAGE_BYTES or request.frame.width * request.frame.height > 16_000_000 or len(request.questions) > 32:
            raise ProviderError("request_too_large", "Prepared image or question batch exceeds worker limits")
        budget = (request.deadline_utc - utcnow()).total_seconds() if request.deadline_utc else 30
        if budget <= 0:
            raise ProviderError("deadline", "Request expired", Status.TIMEOUT)
        body = request_body(request, self.config["worker_id"])
        value = self._call("/infer", body, min(300, budget))
        try:
            if (value["protocol"], value["worker_id"], value["request_id"]) != (1, self.config["worker_id"], body["request_id"]):
                raise ValueError()
            result = decode_result(value["result"], request, self.engine_id, self.engine_version)
            if result.synthetic != self.synthetic:
                raise ValueError()
            from dataclasses import replace
            usage = dict(result.usage) if isinstance(result.usage, dict) else {"provider_usage": result.usage}
            usage["worker"] = {"id": self.config["worker_id"], "transport": self.config["transport"], "request_id": body["request_id"]}
            return replace(result, usage=usage)
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ProviderError("worker_protocol", "Worker result did not match the request") from None
