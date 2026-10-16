"""SSO smoke: log in to Argo CD through Keycloak the way a browser does, then check what each user may do.

platform-admin must be able to sync (dry run) an Application; platform-viewer must see Applications but be refused.
Passwords come from OpenBao and are never printed.
"""
import html
import http.cookiejar
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import openbao


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    pass


def _opener(settings):
    ctx = ssl.create_default_context(cafile=str(settings.root / ".ca" / "ca.crt"))
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                       urllib.request.HTTPCookieProcessor(jar)), jar


def login(settings, username, password):
    """Returns (opener, jar) holding an Argo CD session cookie, or raises RuntimeError."""
    port = settings.cluster("mgmt").https_port
    base = f"https://argocd.mgmt.localhost:{port}"
    opener, jar = _opener(settings)
    page = opener.open(f"{base}/auth/login?return_url={urllib.parse.quote(base + '/applications')}", timeout=20)
    body = page.read().decode()
    m = re.search(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"', body)
    if not m:
        raise RuntimeError(f"no Keycloak login form at {page.geturl()[:120]}")
    action = html.unescape(m.group(1))
    data = urllib.parse.urlencode({"username": username, "password": password, "credentialId": ""}).encode()
    try:
        resp = opener.open(urllib.request.Request(action, data=data, method="POST"), timeout=20)
        resp.read()
        ended = resp.geturl()
    except urllib.error.HTTPError as e:
        # the last hop is Argo CD's web-app route, which only answers browsers; the session cookie is what counts
        ended = e.url
    if not any(c.name == "argocd.token" for c in jar):
        raise RuntimeError(f"login as {username} did not reach Argo CD (ended at {ended[:120]})")
    return opener, base


def _api(opener, url, method="GET", body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def run(settings):
    creds = openbao.get(settings, "mgmt/keycloak") or {}
    results = []
    for user, key, may_sync in (("platform-admin", "platform_admin_password", True),
                                ("platform-viewer", "platform_viewer_password", False)):
        name = f"sso: {user}"
        try:
            opener, base = login(settings, user, creds.get(key, ""))
        except (RuntimeError, urllib.error.URLError, OSError) as e:
            results.append((f"{name} logs in", False, str(e)[:200]))
            continue
        status, info = _api(opener, f"{base}/api/v1/session/userinfo")
        groups = info.get("groups") or []
        results.append((f"{name} logs in", status == 200 and info.get("loggedIn"), f"groups {groups}"))
        status, apps = _api(opener, f"{base}/api/v1/applications")
        names = [a["metadata"]["name"] for a in (apps.get("items") or [])]
        results.append((f"{name} sees applications", status == 200 and bool(names), f"{len(names)} apps"))
        status, _ = _api(opener, f"{base}/api/v1/applications/root/sync", "POST", {"dryRun": True})
        allowed = status == 200
        results.append((f"{name} {'may' if may_sync else 'may not'} sync", allowed == may_sync, f"HTTP {status}"))
    return results


def present(checkout):
    return (checkout / "platform" / "keycloak").is_dir()
