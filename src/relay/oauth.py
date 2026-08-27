"""oauth.py — the OAuth 2.1 core for relay's remote MCP endpoint.

A phone MCP connector (Claude, ChatGPT) drives a self-hosted agent only through
an OAuth 2.1 authorization-code + PKCE flow. This module is the transport-free
core of that flow, stdlib only:

- PKCE S256 (``pkce_challenge`` / ``verify_pkce``);
- signed, expiring access tokens (``issue_access_token`` / ``verify_access_token``,
  HMAC-SHA256, constant-time, injected clock);
- an authorization-code store (one-time, expiring, PKCE- and redirect-bound);
- the authorize and token exchanges (``authorize`` / ``exchange_token``) against a
  pre-registered client -- the path Claude's connector UI takes when you paste a
  client id/secret, so no dynamic registration is needed for v1;
- the discovery documents a connector reads: RFC 9728 protected-resource metadata
  and RFC 8414 authorization-server metadata (S256-only, code grant only).

Everything here is transport-free and deterministic under an injected clock; the
HTTP endpoints (/authorize, /token, /.well-known/*) that wrap it live in the
remote transport. OAuth 2.1 mandates PKCE with S256; this core refuses anything
weaker.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field


class OAuthError(Exception):
    """An OAuth error carrying a spec error code (e.g. ``invalid_grant``)."""

    def __init__(self, code: str, description: str = "") -> None:
        super().__init__(f"{code}: {description}" if description else code)
        self.code = code
        self.description = description


class InvalidToken(Exception):
    """A presented access token failed verification (bad signature or expired)."""


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- PKCE (RFC 7636), S256 only ---

def pkce_challenge(code_verifier: str) -> str:
    """BASE64URL(SHA256(code_verifier)), unpadded -- the S256 code challenge."""
    return _b64url(hashlib.sha256(code_verifier.encode("ascii")).digest())


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    return hmac.compare_digest(pkce_challenge(code_verifier), code_challenge)


# --- access tokens (opaque to the client, HMAC-signed for the resource server) ---

def issue_access_token(
    *, subject: str, secret: str, now: int, ttl: int = 3600, scope: str = "mcp", nonce: str
) -> str:
    """Mint a signed, expiring bearer token: ``base64url(payload).base64url(sig)``.

    Opaque to the client (it just presents it as a Bearer). The resource server
    validates it with ``verify_access_token`` and the same secret. ``nonce`` makes
    two tokens for the same subject/instant distinct (jti)."""
    payload = {"sub": subject, "iat": now, "exp": now + ttl, "scope": scope, "jti": nonce}
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = _b64url(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_access_token(token: str, secret: str, *, now: int) -> dict:
    """Return the token's claims, or raise InvalidToken. Signature is checked in
    constant time before the payload is trusted; expiry is checked against ``now``."""
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        raise InvalidToken("malformed token")
    expected = _b64url(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise InvalidToken("bad signature")
    try:
        claims = json.loads(_b64url_decode(body))
    except (ValueError, json.JSONDecodeError):
        raise InvalidToken("undecodable payload")
    if not isinstance(claims, dict) or "exp" not in claims:
        raise InvalidToken("missing exp")
    if now >= int(claims["exp"]):
        raise InvalidToken("expired")
    return claims


# --- authorization-code flow against a pre-registered client ---

@dataclass(frozen=True)
class RegisteredClient:
    client_id: str
    client_secret: str
    redirect_uris: frozenset[str]


@dataclass(frozen=True)
class AuthCode:
    code: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    exp: int


class AuthCodeStore:
    """One-time, expiring authorization codes. ``consume`` returns a code once and
    only before it expires, so a code cannot be replayed."""

    def __init__(self) -> None:
        self._codes: dict[str, AuthCode] = {}

    def put(self, code: AuthCode) -> None:
        self._codes[code.code] = code

    def consume(self, code: str, *, now: int) -> AuthCode | None:
        entry = self._codes.pop(code, None)
        if entry is None or now >= entry.exp:
            return None
        return entry


@dataclass(frozen=True)
class AuthResult:
    redirect_url: str
    auth_code: AuthCode


def authorize(
    client: RegisteredClient,
    *,
    response_type: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    code: str,
    now: int,
    state: str = "",
    ttl: int = 600,
) -> AuthResult:
    """Validate an authorization request and mint a code, or raise OAuthError.

    Enforces the code grant, a registered redirect_uri, and mandatory S256 PKCE.
    The caller stores ``auth_code`` and 302s the user agent to ``redirect_url``."""
    if response_type != "code":
        raise OAuthError("unsupported_response_type")
    if redirect_uri not in client.redirect_uris:
        raise OAuthError("invalid_request", "unregistered redirect_uri")
    if code_challenge_method != "S256" or not code_challenge:
        raise OAuthError("invalid_request", "S256 PKCE code_challenge is required")
    entry = AuthCode(code, client.client_id, redirect_uri, code_challenge, now + ttl)
    sep = "&" if "?" in redirect_uri else "?"
    url = f"{redirect_uri}{sep}code={code}" + (f"&state={state}" if state else "")
    return AuthResult(url, entry)


def exchange_token(
    client: RegisteredClient,
    store: AuthCodeStore,
    *,
    grant_type: str,
    code: str,
    redirect_uri: str,
    client_secret: str,
    code_verifier: str,
    secret: str,
    now: int,
    nonce: str,
    ttl: int = 3600,
) -> dict:
    """Exchange an authorization code for an access token, or raise OAuthError.

    Verifies the client secret (constant time), consumes the code once, checks the
    client/redirect binding, and verifies the PKCE code_verifier against the stored
    S256 challenge before issuing a token."""
    if grant_type != "authorization_code":
        raise OAuthError("unsupported_grant_type")
    if not hmac.compare_digest(client_secret or "", client.client_secret):
        raise OAuthError("invalid_client")
    entry = store.consume(code, now=now)
    if entry is None:
        raise OAuthError("invalid_grant", "unknown or expired code")
    if entry.client_id != client.client_id or entry.redirect_uri != redirect_uri:
        raise OAuthError("invalid_grant", "code binding mismatch")
    if not verify_pkce(code_verifier or "", entry.code_challenge):
        raise OAuthError("invalid_grant", "PKCE verification failed")
    access = issue_access_token(subject=client.client_id, secret=secret, now=now, ttl=ttl, nonce=nonce)
    return {"access_token": access, "token_type": "Bearer", "expires_in": ttl, "scope": "mcp"}


# --- discovery metadata a connector reads ---

def protected_resource_metadata(resource: str, authorization_server: str) -> dict:
    """RFC 9728: tells a client which authorization server guards this resource."""
    return {
        "resource": resource,
        "authorization_servers": [authorization_server],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp"],
    }


def authorization_server_metadata(issuer: str) -> dict:
    """RFC 8414: advertises the code grant with mandatory S256 PKCE, nothing weaker."""
    issuer = issuer.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "scopes_supported": ["mcp"],
    }
