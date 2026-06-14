"""Model Catalog — รายชื่อ local model ที่ติดตั้งได้ผ่าน Model Manager (M7-2)

ที่มา: PDF "กลุ่มรายชื่อ Local LLM ฟรี" (Qwen + Gemma) → map เป็น Ollama tag จริง
(verified มิ.ย.2026). หลักการ Mix ตามมติ CEO:
- base default = qwen3 (auto ตาม VRAM, ดู VRAMDetector) — ไม่อยู่ในลิสต์นี้แบบบังคับ
- เฉพาะทาง (coder/math/vision) คง **Qwen2.5** เพราะ Qwen3 ไม่มีรุ่นเล็กเฉพาะทาง
- Gemma ใช้ตัวล่าสุด: gemma3 (text) + gemma3n (multimodal = ตัวที่ PDF เรียกผิดว่า "Gemma 4")
- tag "แนะนำ" → Qwen2.5 Coder ทุกขนาด (recommended=True)

lock logic: ถ้า VRAM เครื่อง < min_vram_gb → ล็อก เลือกติดตั้งไม่ได้ (M7-5 UI disable)
size_gb = ขนาดดาวน์โหลดโดยประมาณ · min_vram_gb = VRAM ขั้นต่ำที่รันลื่น (อิงคอลัมน์ PDF)
"""
from __future__ import annotations

# category: general | coder | math | vision | multimodal
CATALOG: list[dict] = [
    # --- Qwen3 ทั่วไป (เพิ่มขนาดอื่นนอกจาก base auto) ---
    {"tag": "qwen3:1.7b", "name": "Qwen3 1.7B", "family": "qwen3", "category": "general",
     "size_gb": 1.4, "min_vram_gb": 3, "recommended": False,
     "desc": "ผู้ช่วยทั่วไปจิ๋ว เบามาก เหมาะเครื่องสเปคต่ำ"},
    {"tag": "qwen3:4b", "name": "Qwen3 4B", "family": "qwen3", "category": "general",
     "size_gb": 2.5, "min_vram_gb": 4, "recommended": False,
     "desc": "ทั่วไปขนาดเล็ก ตรรกะภาษาดีเกินตัว"},
    {"tag": "qwen3:8b", "name": "Qwen3 8B", "family": "qwen3", "category": "general",
     "size_gb": 5.2, "min_vram_gb": 6, "recommended": False,
     "desc": "หัวหน้าทีม/ประสานงาน ภาษาไทยดี (เป็น base default ของการ์ด ~8GB)"},
    {"tag": "qwen3:14b", "name": "Qwen3 14B", "family": "qwen3", "category": "general",
     "size_gb": 9.3, "min_vram_gb": 12, "recommended": False,
     "desc": "ทั่วไปตัวใหญ่ บริบทยาวขึ้น"},
    {"tag": "qwen3:32b", "name": "Qwen3 32B", "family": "qwen3", "category": "general",
     "size_gb": 20.0, "min_vram_gb": 24, "recommended": False,
     "desc": "ทั่วไประดับสูงสุด"},

    # --- Qwen2.5 Coder (⭐ แนะนำทุกขนาด) ---
    {"tag": "qwen2.5-coder:1.5b", "name": "Qwen2.5 Coder 1.5B", "family": "qwen2.5-coder", "category": "coder",
     "size_gb": 1.2, "min_vram_gb": 3, "recommended": True,
     "desc": "ตัวโกงจิ๋วสายโค้ด: เช็ก Syntax พื้นฐาน เขียนสคริปต์สั้น ๆ ดี"},
    {"tag": "qwen2.5-coder:7b", "name": "Qwen2.5 Coder 7B", "family": "qwen2.5-coder", "category": "coder",
     "size_gb": 4.7, "min_vram_gb": 7, "recommended": True,
     "desc": "มหาเทพนักพัฒนาเกม: C#/GDScript/Luau แม่นสุดในงบนี้ — Lead Developer"},
    {"tag": "qwen2.5-coder:14b", "name": "Qwen2.5 Coder 14B", "family": "qwen2.5-coder", "category": "coder",
     "size_gb": 9.0, "min_vram_gb": 12, "recommended": True,
     "desc": "Senior Dev: โครงสร้างโค้ดดีขึ้น เหมาะงานโค้ดยาวที่ 7B เริ่มหลุดบริบท"},
    {"tag": "qwen2.5-coder:32b", "name": "Qwen2.5 Coder 32B", "family": "qwen2.5-coder", "category": "coder",
     "size_gb": 20.0, "min_vram_gb": 24, "recommended": True,
     "desc": "Coder ระดับสูงสุด สำหรับเครื่องสเปคแรง"},

    # --- Qwen2.5 Math ---
    {"tag": "qwen2.5-math:1.5b", "name": "Qwen2.5 Math 1.5B", "family": "qwen2.5-math", "category": "math",
     "size_gb": 1.2, "min_vram_gb": 3, "recommended": False,
     "desc": "นักคำนวณจิ๋ว: แก้โจทย์คณิต/ตรรกะตัวเลขโดยเฉพาะ"},
    {"tag": "qwen2.5-math:7b", "name": "Qwen2.5 Math 7B", "family": "qwen2.5-math", "category": "math",
     "size_gb": 4.7, "min_vram_gb": 7, "recommended": False,
     "desc": "สมองกลฝ่ายบัญชี/ฟิสิกส์: คิดสูตรคำนวณในเกม จัดการสถิติ"},

    # --- Qwen2.5 VL (vision) ---
    {"tag": "qwen2.5vl:7b", "name": "Qwen2.5 VL 7B", "family": "qwen2.5vl", "category": "vision",
     "size_gb": 5.2, "min_vram_gb": 8, "recommended": False,
     "desc": "สายตาออฟฟิศ: อ่านภาพ/UI/แกะโค้ดจาก Screenshot — QA/Tester (context ยาวแนะนำ 12GB)"},

    # --- Gemma3n (multimodal — PDF เรียกผิดว่า Gemma 4) ---
    {"tag": "gemma3n:e2b", "name": "Gemma 3n E2B", "family": "gemma3n", "category": "multimodal",
     "size_gb": 5.6, "min_vram_gb": 6, "recommended": False,
     "desc": "Multimodal จิ๋ว: ภาพ+เสียง + Thinking Mode — สรุปรายงานประชุมจากเสียง"},
    {"tag": "gemma3n:e4b", "name": "Gemma 3n E4B", "family": "gemma3n", "category": "multimodal",
     "size_gb": 7.5, "min_vram_gb": 8, "recommended": False,
     "desc": "Multimodal พกพา: ฉลาดขึ้นจาก E2B บาลานซ์ความเร็ว/เข้าใจคำสั่งซับซ้อน"},

    # --- Gemma3 (text) ---
    {"tag": "gemma3:4b", "name": "Gemma 3 4B", "family": "gemma3", "category": "general",
     "size_gb": 3.3, "min_vram_gb": 5, "recommended": False,
     "desc": "Gemma ทั่วไปขนาดเล็ก"},
    {"tag": "gemma3:12b", "name": "Gemma 3 12B", "family": "gemma3", "category": "general",
     "size_gb": 8.1, "min_vram_gb": 11, "recommended": False,
     "desc": "Multimodal ตรรกะสูง + Thinking Mode ในขนาดประหยัด (PDF เรียก Gemma 4 12B)"},
    {"tag": "gemma3:27b", "name": "Gemma 3 27B", "family": "gemma3", "category": "general",
     "size_gb": 17.0, "min_vram_gb": 20, "recommended": False,
     "desc": "Gemma ตัวใหญ่ ตรรกะ/บริบทดีสุดในตระกูล"},
]

_BY_TAG = {m["tag"]: m for m in CATALOG}


def get(tag: str) -> dict | None:
    """ดึง entry จาก tag — ใช้ตอน install เพื่อ validate ว่า tag อยู่ใน catalog จริง (กัน pull มั่ว)"""
    return _BY_TAG.get(tag)


def get_catalog_with_status(vram_gb: float, installed: set[str] | None = None) -> list[dict]:
    """คืน catalog + flag locked (VRAM ไม่ถึง) + installed (ลงแล้ว)
    installed = set ของ tag ที่ติดตั้งแล้ว (M7-3 จะส่งมาจาก ollama list); None = ยังไม่เช็ก
    """
    installed = installed or set()
    out = []
    for m in CATALOG:
        out.append({
            **m,
            "locked": vram_gb < m["min_vram_gb"],
            "installed": m["tag"] in installed,
        })
    return out
