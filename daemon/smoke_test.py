"""M0-5 smoke test — CrewAI LLM ต่อ Ollama (qwen3:8b) ตอบภาษาไทยได้
รัน: .venv\\Scripts\\python.exe daemon\\smoke_test.py
"""
import sys
import time

from crewai import LLM


def main() -> int:
    llm = LLM(model="ollama/qwen3:8b", base_url="http://localhost:11434")
    print(f"LLM object: {llm.model}")

    start = time.time()
    answer = llm.call("สวัสดี ช่วยแนะนำตัวสั้น ๆ ใน 1 ประโยค")
    elapsed = time.time() - start

    print(f"--- response ({elapsed:.1f}s) ---")
    print(answer)

    if not answer or not answer.strip():
        print("FAIL: empty response")
        return 1
    print("--- SMOKE TEST PASSED ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
