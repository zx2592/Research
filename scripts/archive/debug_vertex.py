
import os
from google import genai
from dotenv import load_dotenv

load_dotenv("d:/工作相关/自动化/AlphaSystem/research/.env")

# Scenario 1: No API Key, No Project (Should fail with missing credentials or similar)
print("Scenario 1: No API Key, No Project")
try:
    client = genai.Client()
    client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents="Hi")
except Exception as e:
    print(f"Caught: {e}")

# Scenario 2: API Key provided, but maybe something forces Vertex?
print("\nScenario 2: API Key, but maybe vertexai=True?")
try:
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key, vertexai=True) # MISSING PROJECT
    client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents="Hi")
except Exception as e:
    print(f"Caught: {e}")

# Scenario 3: API Key, vertexai=False (Should work)
print("\nScenario 3: API Key, vertexai=False")
try:
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key, vertexai=False)
    client.models.generate_content(model="gemini-3.1-flash-lite-preview", contents="Hi")
    print("Success")
except Exception as e:
    print(f"Caught: {e}")
