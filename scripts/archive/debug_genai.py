
import os
from google import genai
from dotenv import load_dotenv

load_dotenv("d:/工作相关/自动化/AlphaSystem/research/.env")

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

print(f"Client API Key: {client._api_key if hasattr(client, '_api_key') else 'N/A'}")
print(f"Vertex AI Mode: {client._vertexai if hasattr(client, '_vertexai') else 'N/A'}")

try:
    # Try to get models to see if it triggers the error
    for m in client.models.list(config={'page_size': 1}):
        print(f"Model: {m.name}")
        break
except Exception as e:
    print(f"Error during list_models: {e}")

# Check if model name triggers it
model_name = "gemini-3.1-flash-lite-preview"
try:
    print(f"Testing generate_content with {model_name}...")
    response = client.models.generate_content(
        model=model_name,
        contents="Hi"
    )
    print("Success")
except Exception as e:
    print(f"Error during generate_content: {e}")
