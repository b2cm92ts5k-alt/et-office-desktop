# QA Gate M2 — Checklist & ผลทดสอบ (M2-13)

Gate อัตโนมัติ: `powershell -ExecutionPolicy Bypass -File tools\qa_m2.ps1`
(เปลี่ยน wallpaper จริงชั่วคราว + จอดำแวบ ~8 วิ ระหว่างทดสอบ fullscreen pause)

## ผลรันล่าสุด — Windows 10 Pro 19045, RTX 2060 SUPER (2026-06-12)

| ข้อ | ผล | รายละเอียด |
|---|---|---|
| Attach เป็น wallpaper (WorkerW embed) | ✅ | sibling-after-SHELLDLL_DefView layout |
| Conflict guard pause Wallpaper Engine ก่อน attach | ✅ | ทดสอบกับ WE จริงที่รันอยู่ |
| GPU เพิ่มจาก baseline < 20% | ✅ | baseline 16.6% → 23.6% = **delta 7%** (max 43% ช่วง attach) |
| Pause เมื่อ fullscreen ทับ | ✅ | flag → 2fps + tree paused ภายใน ~5 วิ |
| Resume เมื่อ fullscreen ปิด | ✅ | กลับ 30fps อัตโนมัติ |
| ปิดด้วย WM_CLOSE → detach + คืน WE | ✅ | desktop กลับสภาพเดิม |

หมายเหตุการวัด GPU:
- ใช้ delta จาก baseline (nvidia-smi ทั้ง GPU) — ตัวเลข absolute หลอกได้
  เพราะรวมแอปอื่น + util% โป่งตอน clock ต่ำ
- Windows "GPU Engine" perf counters ผ่าน `Get-Counter` ให้ raw 100ns sum ใช้ไม่ได้
- เครื่องเป้าหมายต่ำสุดตามสเปค (GTX 1060) ยังไม่ได้วัดจริง — คาด delta สูงกว่านี้
  แต่ scene เป็น 2D เบามาก

## ⬜ ค้างทดสอบ: Windows 11 (ไม่มีเครื่อง — ทำมือเมื่อหาได้)

1. ⬜ `tools\wallpaper.ps1 -Probe` หา WorkerW เจอ (Win11 บาง build เปลี่ยน layout — script มี fallback 3 แบบ)
2. ⬜ รัน gate เต็ม: `tools\qa_m2.ps1` ผ่านทุกข้อ
3. ⬜ Desktop icons ยังคลิกได้ / right-click desktop ปกติ ระหว่าง wallpaper ทำงาน
4. ⬜ ทดสอบบนจอ scale ≠ 100% (Win11 default 150%) — ภาพไม่เบลอ/ไม่ล้น
5. ⬜ ถ้ามี Wallpaper Engine/Lively บนเครื่องนั้น → conflict guard จัดการถูก

ผ่านครบเมื่อไหร่ → อัพเดตตารางนี้ + ปิดข้อนี้ใน board ได้สมบูรณ์
