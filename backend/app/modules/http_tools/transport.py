"""Fixed HTTPS JSON targets, public IPv4 pinning, original TLS identity, no redirects/proxies."""

import asyncio
import ipaddress
import json
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException

from app.core.errors import fail
from app.core.json_contracts import bounded_json

HOST = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
DNS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="http-dns")
DNS_SLOTS = threading.BoundedSemaphore(8)


def canonical_url(value):
    if any(ord(char) <= 32 or ord(char) > 126 for char in value) or "\\" in value:
        fail(
            422,
            "HTTP_URL_INVALID",
            "Use a public HTTPS URL with encoded path characters and no credentials.",
        )
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        fail(422, "HTTP_URL_INVALID", "The HTTP endpoint URL is invalid.")
    if (
        parsed.scheme != "https"
        or port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not HOST.fullmatch(host)
        or host.endswith((".local", ".internal", ".localhost"))
    ):
        fail(
            422,
            "HTTP_URL_INVALID",
            "Use a public HTTPS endpoint on port 443. Put credentials in headers and query values in tool input.",
        )
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        fail(
            422,
            "HTTP_URL_INVALID",
            "HTTP tools require a public DNS hostname rather than an IP address.",
        )
    return str(httpx.URL(urlunsplit(("https", host, parsed.path or "/", "", ""))))


def public_address(host, timeout=3.0):
    # IPv4-only is an explicit v1 boundary. It avoids transition/NAT64 address
    # ambiguity while covering the common JSON SaaS APIs targeted by this slice.
    if not DNS_SLOTS.acquire(blocking=False):
        fail(503, "HTTP_DNS_BUSY", "Endpoint checks are busy. Try again shortly.")
    try:
        future = DNS_POOL.submit(socket.getaddrinfo, host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except Exception:
        DNS_SLOTS.release()
        fail(503, "HTTP_DNS_BUSY", "Endpoint checks are temporarily unavailable.")
    # Timed-out OS lookups retain their slot until they actually finish. This
    # bounds the worker pool and its queue even if the system resolver stalls.
    future.add_done_callback(lambda _: DNS_SLOTS.release())
    try:
        answers = future.result(timeout=max(0.001, min(3.0, timeout)))
    except FutureTimeout:
        future.cancel()
        fail(504, "HTTP_DNS_TIMEOUT", "The endpoint DNS check timed out.")
    except OSError:
        fail(502, "HTTP_DNS_FAILED", "The endpoint did not resolve to a public IPv4 service.")
    if not answers or len(answers) > 32:
        fail(502, "HTTP_ENDPOINT_BLOCKED", "The endpoint did not resolve to an allowed network.")
    addresses = []
    for answer in answers:
        try:
            address = ipaddress.IPv4Address(answer[4][0])
        except ValueError:
            fail(502, "HTTP_ENDPOINT_BLOCKED", "The endpoint resolved to a blocked network.")
        if not address.is_global or address.is_multicast or address.is_reserved:
            fail(502, "HTTP_ENDPOINT_BLOCKED", "The endpoint resolved to a blocked network.")
        addresses.append(str(address))
    return addresses[0]


def scrub(value, secret):
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[redacted credential]")
    if isinstance(value, list):
        return [scrub(item, secret) for item in value]
    if isinstance(value, dict):
        return {scrub(key, secret): scrub(item, secret) for key, item in value.items()}
    return value


async def exchange(spec, secret, arguments, address, timeout):
    parsed = urlsplit(spec["url"])
    url = httpx.URL(spec["url"]).copy_with(host=address)
    headers = {
        "Host": parsed.hostname,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "User-Agent": "FlowForgeAI/0.1",
    }
    if spec["auth_mode"] != "none":
        headers[spec["auth_header"]] = ("Bearer " if spec["auth_mode"] == "bearer" else "") + secret
    payload = None
    if spec["method"] == "GET":
        if any(
            not isinstance(value, (str, int, float, bool, type(None)))
            for value in arguments.values()
        ):
            fail(422, "HTTP_QUERY_INVALID", "GET tool fields must be simple query values.")
        query = urlencode(
            {
                key: str(value).lower()
                if isinstance(value, bool)
                else ""
                if value is None
                else value
                for key, value in arguments.items()
            }
        )
        if len(query.encode()) > 4096:
            fail(422, "HTTP_QUERY_TOO_LARGE", "GET query values exceed the supported size.")
        url = url.copy_with(query=query.encode())
    else:
        payload = json.dumps(arguments, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(
        follow_redirects=False,
        trust_env=False,
        verify=True,
        timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
    ) as client:
        async with client.stream(
            spec["method"],
            url,
            headers=headers,
            content=payload,
            extensions={"sni_hostname": parsed.hostname},
        ) as response:
            if not 200 <= response.status_code < 300:
                fail(
                    502,
                    "HTTP_STATUS_" + str(response.status_code),
                    "The target API rejected the request. Check its required permissions and input.",
                )
            if response.headers.get("content-encoding", "identity").lower() not in {"identity", ""}:
                fail(
                    502,
                    "HTTP_ENCODING_UNSUPPORTED",
                    "The target returned an unsupported encoded response.",
                )
            length = response.headers.get("content-length")
            if length and (not length.isdecimal() or int(length) > 65536):
                fail(
                    502,
                    "HTTP_RESULT_TOO_LARGE",
                    "The target returned an invalid or oversized response.",
                )
            content = bytearray()
            async for chunk in response.aiter_raw():
                content.extend(chunk)
                if len(content) > 65536:
                    fail(502, "HTTP_RESULT_TOO_LARGE", "The target returned too much data.")
            if content:
                media = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if media != "application/json" and not (
                    media.startswith("application/") and media.endswith("+json")
                ):
                    fail(502, "HTTP_RESPONSE_INVALID", "The target must return JSON.")
                body = json.loads(content.decode("utf-8"))
            else:
                body = None
            if parsed.hostname == "slack.com" and parsed.path == "/api/chat.postMessage" and isinstance(body, dict) and body.get("ok") is False:
                # Slack can reject a request with HTTP 200. Never record it as
                # a successful write, and do not echo arbitrary response text.
                code = body.get("error")
                known = {"invalid_auth", "token_revoked", "missing_scope", "not_in_channel", "channel_not_found", "is_archived", "ratelimited", "no_permission", "account_inactive"}
                suffix = code.upper() if isinstance(code, str) and code in known else "REQUEST_REJECTED"
                fail(502, "SLACK_" + suffix, "Slack rejected this message. Check the tool token, chat:write permission and bot membership in the selected channel before replaying.")
            result = scrub({"status_code": response.status_code, "body": body}, secret)
            bounded_json(result, max_bytes=65536)
            return result


def request(spec, secret, arguments, timeout=12):
    bounded_json(arguments, max_bytes=65536)
    began = time.monotonic()
    host = urlsplit(canonical_url(spec["url"])).hostname
    address = public_address(host, timeout=min(3.0, timeout))
    remaining = min(12.0, timeout) - (time.monotonic() - began)
    if remaining <= 0:
        fail(504, "HTTP_TIMEOUT", "The HTTP request exceeded its deadline.")

    async def bounded():
        return await asyncio.wait_for(
            exchange(spec, secret, arguments, address, remaining), timeout=remaining
        )

    try:
        return asyncio.run(bounded())
    except HTTPException:
        raise
    except (TimeoutError, httpx.TimeoutException):
        fail(
            504,
            "HTTP_OUTCOME_UNKNOWN",
            "The HTTP outcome could not be confirmed. Inspect the target service before replaying.",
        )
    except Exception:
        fail(
            502,
            "HTTP_OUTCOME_UNKNOWN",
            "The HTTP outcome could not be confirmed. Inspect the target service before replaying.",
        )
