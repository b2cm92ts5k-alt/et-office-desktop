# ADR M4-1: Sidebar host = pywebview (ไม่ใช่ Tauri)

**สถานะ:** ตัดสินใจแล้ว — 2026-06-11

## บริบท
Technical blueprint เปิดทางเลือกไว้สองทาง: Python webview2 (pywebview) กับ Tauri (Rust)

## ตัดสินใจ: pywebview + EdgeChromium (WebView2)

เหตุผล:
1. **Stack เป็น Python ล้วน** — daemon, tray (pystray), tools เป็น Python หมดแล้ว
   ไม่ต้องเพิ่ม Rust toolchain ให้ contributor และไม่ต้อง build pipeline ที่สอง
2. **WebView2 ติดมากับ Windows 10/11** (มากับ Edge) — ไม่บวมขนาด installer
3. **venv เดียวรันได้ทั้งระบบ** — `pip install pywebview` จบ
4. Sidebar คุยกับ daemon ตรง ๆ จาก JavaScript (HTTP + WS port 8797)
   → ฝั่ง Python ของ sidebar ทำแค่ window management (ขนาด/ตำแหน่ง/frameless)
   โค้ดส่วนที่ผูกกับ pywebview จึงบางมาก — ถ้าวันหน้าอยากย้ายไป Tauri
   ย้ายแค่ host ~100 บรรทัด ส่วน HTML/JS ใช้ต่อได้ทั้งหมด

## ผลที่ตามมา
- ต้องการ WebView2 Runtime (มีใน Win10 19045 ของเครื่อง dev แล้ว)
- หน้าต่าง transparent จริงทำได้จำกัดบน pywebview — ใช้พื้นทึบสีเข้ม
  (#0a0a14) แทน semi-transparent ไปก่อน (review อีกครั้งตอน M4-11)
- รัน: `.venv\Scripts\python.exe sidebar\host.py`

## บทเรียนระหว่างทำ (สำคัญ)
1. **ห้ามใช้ `js_api` bridge ของ pywebview** — บนเครื่อง dev (pywebview 6.2.1
   + WebView2 149) การ inject bridge ทำให้ JS ทั้งหน้าพังเงียบ ๆ
   (fetch/promise ไม่ resolve, stderr มี COM error `ICoreWebView2Controller4`)
   → ปุ่มหุบ/ขยายส่งสัญญาณผ่าน daemon แทน: JS `POST /event sidebar.toggle`
   → host มี WS client ฟังอยู่ → resize หน้าต่าง
2. **หน้าเพจต้อง serve ผ่าน daemon** (`/sidebar/` StaticFiles) ไม่ใช่ `file://`
   — same-origin ตัดปัญหา CORS/origin null ทั้งหมด
3. QA hooks ใช้ query param (`?qa_task=...&qa_toggle=1`) แทน `evaluate_js`
   ด้วยเหตุผลเดียวกับข้อ 1
