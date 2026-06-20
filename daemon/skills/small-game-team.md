---
name: small-game-team
description: ใช้เมื่อต้องทำเกมเล็กเป็นทีม (วางระบบเกม ออกแบบ ทำ asset เขียน gameplay)
when: [เกม, game, gameplay, เลเวล, level, ตัวละคร, sprite, สไปรท์, gdd, mechanic, กลไกเกม, ด่าน, prototype เกม]
tools: [list_dir, read_file, write_file, mkdir, powershell, git_status, git_commit]
---
# สูตร: ทำเกมเล็กเป็นทีม (Sub-Agent)

เกมต้องหลายศาสตร์ทำร่วมกัน — orchestrator แตกงานตามเฟสนี้ มอบให้ role ที่ตรง:

**เฟส 1 — ออกแบบ (game-designer)**
- เขียน GDD สั้น: core loop, กลไกหลัก (mechanics), เงื่อนไขแพ้/ชนะ, progression → `write_file` `design/GDD.md`
- กันหลงทาง: เริ่มจาก prototype เล็กที่เล่นได้จริงก่อน อย่าใส่ฟีเจอร์เกินจำเป็น

**เฟส 2 — ศิลป์/asset (game-artist / pixel-artist)**
- ลิสต์ asset ที่ต้องใช้ตาม GDD (ตัวละคร, ฉาก, UI) + สไตล์/ขนาด/พาเลตต์ → spec หรือ generate
- จัดเก็บเป็นระเบียบใน `assets/` (`mkdir` แยกหมวด)

**เฟส 3 — โค้ด gameplay (game-programmer)**
- ทำกลไกตาม GDD ทีละชิ้น (เคลื่อนที่ → ชน → แพ้/ชนะ → คะแนน) เข้ากับ engine ที่โปรเจกต์ใช้
- เขียนแล้ว `powershell` รัน/เทสให้เล่นได้จริงก่อนไปกลไกถัดไป

**เฟส 4 — ทดสอบ + รวม**
- เล่นจริงรอบหนึ่ง จดบั๊ก/จุดสนุก-ไม่สนุก → แก้ → `git_commit`
- รายงาน CEO: ทำอะไรไปแล้ว เล่นได้แค่ไหน เหลืออะไร

กฎ: ทำให้ "เล่นได้จริง" ก่อนเสมอ (playable slice) แล้วค่อยขัดเกลา — อย่าเขียนระบบใหญ่ที่ยังรันไม่ได้ทิ้งไว้
