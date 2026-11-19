"""Replaceable JSON ingestion adapter for a provisioned gateway."""

import ipaddress
import json
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def validate_url(url):
    target = urlparse(url)
    try:
        loopback = ipaddress.ip_address(target.hostname or "").is_loopback
    except ValueError:
        loopback = target.hostname == "localhost"
    if (target.scheme != "https" and not (target.scheme == "http" and loopback)
            or not target.hostname or target.username or target.password or target.fragment):
        raise ValueError("Cloud ingestion requires HTTPS, or HTTP to a loopback mock.")
    return url


class HttpCloud:
    def __init__(self, url, token, timeout):
        self.url, self.token, self.timeout = validate_url(url), token, timeout
        self.opener = build_opener(NoRedirect())

    def send(self, event):
        data = {k: v for k, v in event.items() if k not in {
            "clip", "clip_pending", "cloud_status", "attempts", "last_error"
        }}
        headers = {"Content-Type": "application/json", "Idempotency-Key": event["id"]}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = Request(self.url, data=json.dumps(data, ensure_ascii=False).encode("utf-8"), headers=headers)
        with self.opener.open(request, timeout=self.timeout) as response:
            if not 200 <= response.status < 300:
                raise OSError("Cloud returned HTTP {}".format(response.status))
