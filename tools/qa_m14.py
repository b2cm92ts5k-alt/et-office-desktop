"""QA Gate M14 — Provider Accounts & OAuth (M14-1..M14-11)

รันแบบ import ตรง (ไม่ต้องมี daemon): python tools/qa_m14.py
ครอบคลุม: ProviderAccountStore + DPAPI, provider matrix (+grok/+deepseek), catalog+pricing,
account_id resolution, api-key validate, Claude OAuth (PKCE/exchange/refresh), /accounts routes,
group-by-account, UI wiring + secret ไม่หลุด.

network จริงไม่ถูกเรียก — oauth ใช้ mock token server, validate เทสแค่โครง (bad key → ok:False).
account_store ชี้ temp dir เสมอ (ไม่แตะ cloud_accounts จริง).
"""
from __future__ import annotations

import http.server
import json
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    _results.append((bool(ok), name, info))
    print(("PASS" if ok else "FAIL"), "-", name, (f"  [{info}]" if info else ""))


def _mock_token_server() -> tuple[str, object]:
    """server เล็ก ๆ ตอบ token ทั้ง authorization_code และ refresh_token"""
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            d = dict(urllib.parse.parse_qsl(self.rfile.read(n).decode()))
            if d.get("grant_type") == "refresh_token":
                body = {"access_token": "AT-REFRESHED", "refresh_token": "RT-NEW", "expires_in": 3600}
            else:
                body = {"access_token": "AT-INIT", "refresh_token": "RT-INIT", "expires_in": 3600, "scope": "user:inference"}
            out = json.dumps(body).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.end_headers(); self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/tok", srv


def main() -> None:
    from daemon.adapters import llm_adapter as LA
    from daemon.models.schemas import LLMConfig
    from daemon.services import account_store as AS
    from daemon.services import oauth_flow as OF

    # account_store → temp (ไม่แตะของจริง) + legacy file สำหรับเทส migrate
    tmp = Path(tempfile.mkdtemp())
    AS._DATA_DIR = tmp
    AS.ENC_PATH = tmp / "cloud_accounts.enc"
    AS.PLAIN_PATH = tmp / "cloud_accounts.json"
    AS.LEGACY_KEYS_PATH = tmp / "cloud_keys.json"

    # ---------- M14-2 provider matrix ----------
    print("--- M14-2 provider matrix (+grok +deepseek) ---")
    check("ENV_KEY_MAP มี grok+deepseek", "grok" in LA.ENV_KEY_MAP and "deepseek" in LA.ENV_KEY_MAP,
          ",".join(LA.ENV_KEY_MAP))
    check("deepseek เป็น native prefix", LA.LLM_PREFIX.get("deepseek") == "deepseek")
    check("grok เป็น openai-compat (base_url)", "grok" in LA.CLOUD_BASE_URL and "x.ai" in LA.CLOUD_BASE_URL["grok"])
    check("DEFAULT_CLOUD_MODELS ครบ 5", all(p in LA.DEFAULT_CLOUD_MODELS for p in ("claude", "gemini", "openai", "grok", "deepseek")))
    check("LLMConfig รับ grok/deepseek", LLMConfig(provider="grok").provider == "grok" and LLMConfig(provider="deepseek").provider == "deepseek")

    # ---------- M14-3 catalog + pricing ----------
    print("--- M14-3 catalog + pricing ---")
    check("grok catalog >=4 ตัว", len(LA.cloud_models("grok")) >= 4)
    check("deepseek catalog >=2 ตัว", len(LA.cloud_models("deepseek")) >= 2)
    check("cloud_price grok-4.3 มีค่า", LA.cloud_price("grok", "grok-4.3") is not None)
    from daemon.services.cost_guard import cost_guard
    usd = cost_guard.record("deepseek", "deepseek-v4-flash", 1_000_000, 1_000_000)
    check("cost_guard คิดเงิน deepseek (per-model)", usd > 0, f"${usd:.3f}")

    # ---------- M14-1 ProviderAccountStore + DPAPI ----------
    print("--- M14-1 ProviderAccountStore + DPAPI ---")
    AS.account_store._accounts = []
    acc = AS.account_store.add_api_key("grok", "lbl", "xai-SUPERSECRET12345")
    check("add api_key คืน masked (ไม่มี key ดิบ)", "key" not in acc and acc.get("masked", "").endswith("2345"))
    enc_exists = AS.ENC_PATH.exists()
    raw = AS.ENC_PATH.read_bytes() if enc_exists else b""
    check("ไฟล์เข้ารหัส DPAPI (มี .enc)", enc_exists, "win32crypt" if enc_exists else "fallback plaintext")
    check("blob ไม่มี secret ดิบ", enc_exists and b"SUPERSECRET" not in raw)
    # reload จากดิสก์ → decrypt ได้
    s2 = AS.ProviderAccountStore()
    check("reload+decrypt ได้ secret กลับมา", s2.get(acc["id"])["secret"]["key"] == "xai-SUPERSECRET12345")
    check("public ไม่คาย secret", all("key" not in p and "access_token" not in p for p in s2.all_public()))
    check("delete ได้", s2.delete(acc["id"]) and len(s2.all_public()) == 0)

    # migrate legacy cloud_keys.json
    AS.LEGACY_KEYS_PATH.write_text(json.dumps(
        [{"id": "old1", "provider": "gemini", "label": "เก่า", "key": "AIzaOLDKEY"}]), encoding="utf-8")
    AS.ENC_PATH.unlink(missing_ok=True)
    AS.PLAIN_PATH.unlink(missing_ok=True)
    s3 = AS.ProviderAccountStore()
    migrated = s3.get("old1")
    check("migrate cloud_keys.json → api_key account", bool(migrated) and migrated["auth_mode"] == "api_key"
          and migrated["secret"]["key"] == "AIzaOLDKEY")

    # ---------- M14-4 account_id resolution ----------
    print("--- M14-4 account_id resolution ---")
    check("LLMConfig มี account_id + key_id", hasattr(LLMConfig(), "account_id") and hasattr(LLMConfig(), "key_id"))
    AS.account_store._accounts = [
        {"id": "a_api", "provider": "grok", "label": "x", "auth_mode": "api_key", "secret": {"key": "K-API"}},
    ]
    AS.account_store._save = lambda: None
    check("resolve api_key account → key", LA._resolve_cloud_key("grok", account_id="a_api") == "K-API")
    check("account_id ว่าง + ไม่มี env → ''", LA._resolve_cloud_key("grok") == "")

    # ---------- M14-6/7 Claude OAuth (PKCE) + refresh ----------
    print("--- M14-6/7 Claude OAuth (PKCE) + refresh ---")
    token_url, srv = _mock_token_server()
    OF.PROVIDER_OAUTH["claude"] = {"authorize_url": "https://claude.ai/oauth/authorize",
                                   "token_url": token_url, "client_id": "TESTCID", "scope": "user:inference"}
    OF._pending.clear()
    v, c = OF.pkce_pair()
    check("PKCE pair (verifier+challenge ต่างกัน)", v and c and v != c)
    st = OF.start("claude", "http://localhost:8797/accounts/oauth/callback")
    check("authorize_url มี PKCE S256 + client_id", "code_challenge=" in st["authorize_url"]
          and "code_challenge_method=S256" in st["authorize_url"] and "client_id=TESTCID" in st["authorize_url"])
    prov, tok = OF.exchange(st["state"], "AUTHCODE")
    check("exchange → access+refresh token", prov == "claude" and tok["access_token"] == "AT-INIT" and tok["refresh_token"] == "RT-INIT")
    try:
        OF.exchange("BOGUS", "x"); bad_ok = False
    except ValueError:
        bad_ok = True
    check("bad state ถูกปฏิเสธ (กัน CSRF)", bad_ok)
    # lazy refresh: token หมดอายุ → resolver refresh เอง
    AS.account_store._accounts = [{"id": "oc", "provider": "claude", "label": "max", "auth_mode": "oauth",
                                   "secret": {"access_token": "AT-OLD", "refresh_token": "RT-INIT",
                                              "expires_at": time.time() - 5, "scope": ""}}]
    refreshed = LA._resolve_cloud_key("claude", account_id="oc")
    check("lazy refresh token หมดอายุ → ใหม่", refreshed == "AT-REFRESHED")
    check("store rotate refresh token", AS.account_store.get("oc")["secret"]["refresh_token"] == "RT-NEW")
    srv.shutdown()
    OF.PROVIDER_OAUTH["claude"]["client_id"] = ""  # เคลียร์ค่าเทส — กัน route เปิด browser จริง + ให้เทส 400 ด้านล่าง valid

    # ---------- M14-5/8/9 routes (TestClient) ----------
    print("--- M14-5/8/9 /accounts + /models/available ---")
    from fastapi.testclient import TestClient
    from daemon.main import app
    cl = TestClient(app)
    AS.account_store._accounts = [
        {"id": "cl1", "provider": "claude", "label": "Claude Max", "auth_mode": "oauth",
         "secret": {"access_token": "x", "refresh_token": "r", "expires_at": 9e9, "scope": ""}},
        {"id": "gr1", "provider": "grok", "label": "xai", "auth_mode": "api_key", "secret": {"key": "k"}},
    ]
    r = cl.get("/accounts")
    check("GET /accounts 200 + providers", r.status_code == 200 and len(r.json()["providers"]) == 5)
    check("list masked ไม่มี token/key", all("access_token" not in a and "key" not in a for a in r.json()["accounts"]))
    r2 = cl.post("/accounts/oauth/start", json={"provider": "claude"})
    check("oauth/start ไม่มี client_id → 400", r2.status_code == 400)
    r3 = cl.post("/accounts/oauth/start", json={"provider": "grok"})
    check("oauth/start provider ไม่รองรับ → 400", r3.status_code == 400)
    opts = cl.get("/models/available").json()["options"]
    claude_opts = [o for o in opts if o.get("account_id") == "cl1"]
    check("group-by-account: 1 บัญชี Claude → หลาย model", len(claude_opts) >= 3,
          ",".join(o["model"] for o in claude_opts))
    check("ทุก option มี account_id field", all("account_id" in o for o in opts))

    # ---------- M14-5 validate (โครง) ----------
    print("--- M14-5 validate_cloud_key ---")
    check("validate มี endpoint ครบ 5 provider", all(p in LA._VALIDATE_EP for p in ("claude", "gemini", "openai", "grok", "deepseek")))
    bad = LA.validate_cloud_key("openai", "sk-bogus-key-xxx", timeout=6)
    check("validate key ปลอม → ok:False (ไม่ throw)", bad.get("ok") is False)

    # ---------- M14-10/11 UI wiring ----------
    print("--- M14-10/11 UI wiring ---")
    web = Path(__file__).resolve().parent.parent / "sidebar" / "web"
    appjs = (web / "app.js").read_text(encoding="utf-8")
    html = (web / "index.html").read_text(encoding="utf-8")
    check("app.js มีฟังก์ชัน account ครบ", all(f in appjs for f in ("loadAccounts", "connectOAuth", "addAccountKey", "deleteAccount")))
    check("model dropdown พา account_id (3-part)", 'o.account_id || ""' in appjs and "p[2]" in appjs)
    check("index.html มี ACCOUNTS section ids", all(f'id="{i}"' in html for i in ("acc-oauth", "acc-provider", "acc-key", "accounts-list")))
    check("M14-11 banner Subscription vs API", "ใช้ยิงจากแอปไม่ได้" in html and "มีแค่ Claude" in html)
    check("provider select มี grok+deepseek", 'value="grok"' in html and 'value="deepseek"' in html)

    # ---------- สรุป ----------
    passed = sum(1 for ok, _, _ in _results if ok)
    total = len(_results)
    print(f"\n===== M14 QA: {passed}/{total} PASS =====")
    if passed != total:
        print("FAILED:", [n for ok, n, _ in _results if not ok])
        sys.exit(1)


if __name__ == "__main__":
    main()
