"""
test_models.py — 测试 Gemini 3.1 模型 API 连通性
用法: python test_models.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from google import genai

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("❌ GEMINI_API_KEY not found in .env")
    sys.exit(1)

client = genai.Client(api_key=api_key)

MODELS = {
    "CLI (VPS) — gemini-3.1-flash-lite-preview": "gemini-3.1-flash-lite-preview",
    "IDE (Pro) — gemini-3.1-pro-preview":         "gemini-3.1-pro-preview",
}

for label, model_name in MODELS.items():
    print(f"\n🔍 Testing: {label}")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents="用一句简体中文回复：API 连接成功。"
        )
        print(f"  ✅ OK — 响应: {response.text.strip()}")
    except Exception as e:
        print(f"  ❌ FAILED — {type(e).__name__}: {e}")
