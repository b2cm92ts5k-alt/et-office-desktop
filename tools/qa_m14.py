"""QA Gate M14 — Provider Accounts (API key) (M14-1..M14-11)

รันแบบ import ตรง (ไม่ต้องมี daemon): python tools/qa_m14.py
ครอบคลุม: ProviderAccountStore + DPAPI, provider matrix (+grok/+deepseek), catalog+pricing,
account_id resolution, api-key validate, /accounts routes, group-by-account, UI wiring + secret ไม่หลุด.

(OAuth ถอดออก — Anthropic/Google ห้าม third-party ใช้ OAuth subscription, ผิด ToS.)
network จริงไม่ถูกเรียก — validate เทสแค่โครง (bad key → ok:False).
account_store ชี้ temp dir เสมอ (ไม่แตะ cloud_accounts จริง).
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    _results.append((bool(ok), name, info))
    print(("PASS" if ok else "FAIL"), "-", name, (f"  [{info}]" if info else ""))


def main() -> None:
    from daemon.adapters import llm_adapter as LA
    from daemon.models.schemas import LLMConfig
    from daemon.services import account_store as AS

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

    # ---------- M14: OAuth ถอดออก (ยืนยันไม่มี oauth_flow + route แล้ว) ----------
    print("--- M14: OAuth removed (compliance) ---")
    check("ลบ oauth_flow.py แล้ว", not (Path(LA.__file__).resolve().parent.parent / "services" / "oauth_flow.py").exists())
    import importlib.util
    check("import oauth_flow ไม่ได้แล้ว", importlib.util.find_spec("daemon.services.oauth_flow") is None)

    # ---------- M14-5/8/9 routes (TestClient) ----------
    print("--- M14-5/8/9 /accounts + /models/available ---")
    from fastapi.testclient import TestClient
    from daemon.main import app
    cl = TestClient(app)
    AS.account_store._accounts = [
        {"id": "cl1", "provider": "claude", "label": "Claude key", "auth_mode": "api_key", "secret": {"key": "kc"}},
        {"id": "gr1", "provider": "grok", "label": "xai", "auth_mode": "api_key", "secret": {"key": "k"}},
    ]
    r = cl.get("/accounts")
    check("GET /accounts 200 + providers", r.status_code == 200 and len(r.json()["providers"]) == 5)
    check("list masked ไม่มี key ดิบ", all("key" not in a for a in r.json()["accounts"]))
    check("oauth route ถูกถอด (start → 404/405)", cl.post("/accounts/oauth/start", json={"provider": "claude"}).status_code in (404, 405))
    opts = cl.get("/models/available").json()["options"]
    claude_opts = [o for o in opts if o["provider"] == "claude"]
    check("provider มี credential → catalog 1 ชุด (ไม่ซ้ำตามจำนวน key)", len(claude_opts) >= 3,
          ",".join(o["model"] for o in claude_opts))
    # มี account claude 1 + grok 1 → ไม่ควรมี model ซ้ำ (เช่น claude opus โผล่ครั้งเดียว)
    dup = [o["provider"] + "/" + o["model"] for o in opts]
    check("ไม่มี model ซ้ำใน dropdown", len(dup) == len(set(dup)))
    check("key dropdown filter ตาม provider", cl.get("/accounts?provider=grok").status_code == 200)

    # ---------- M14-5 validate (โครง) ----------
    print("--- M14-5 validate_cloud_key ---")
    check("validate มี endpoint ครบ 5 provider", all(p in LA._VALIDATE_EP for p in ("claude", "gemini", "openai", "grok", "deepseek")))
    bad = LA.validate_cloud_key("openai", "sk-bogus-key-xxx", timeout=6)
    check("validate key ปลอม → ok:False (ไม่ throw)", bad.get("ok") is False)

    # ---------- M14 UI wiring ----------
    print("--- M14 UI wiring ---")
    web = Path(__file__).resolve().parent.parent / "sidebar" / "web"
    appjs = (web / "app.js").read_text(encoding="utf-8")
    html = (web / "index.html").read_text(encoding="utf-8")
    check("model dropdown = provider|model (1 บรรทัด/model)", 'o.provider + "|" + o.model;' in appjs)
    check("LOGIN/OAuth UI ถูกถอด", "connectOAuth" not in appjs and 'id="acc-oauth"' not in html and "LOGIN — Claude subscription" not in html)
    check("API KEYS section + provider grok/deepseek", "API KEYS" in html and 'value="grok"' in html and 'value="deepseek"' in html)
    # M14 consolidation — key store เดียว (account_store DPAPI), เลิก /settings/keys ใน UI
    check("UI key form ใช้ /accounts/api-key (ไม่ใช่ /settings/keys)", "/accounts/api-key" in appjs and "/settings/keys" not in appjs)
    # UX 2-step: เลือก model → เลือก key/บัญชีจาก dropdown แยก (อ่าน /accounts)
    check("m-key dropdown มี + อ่าน /accounts", "refreshKeyDropdown" in appjs and "/accounts?provider=" in appjs and 'id="m-key"' in html)
    check("saveModel ผูก account_id จาก key dropdown", "llm.account_id = keyRow" in appjs)

    # ---------- สรุป ----------
    passed = sum(1 for ok, _, _ in _results if ok)
    total = len(_results)
    print(f"\n===== M14 QA: {passed}/{total} PASS =====")
    if passed != total:
        print("FAILED:", [n for ok, n, _ in _results if not ok])
        sys.exit(1)


if __name__ == "__main__":
    main()
