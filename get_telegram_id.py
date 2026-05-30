import requests
import time
import sys

def get_chat_id(token):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    print(f"Checking for updates on bot...")
    try:
        response = requests.get(url)
        data = response.json()
        
        if not data.get('ok'):
            print(f"Error: {data.get('description')}")
            return

        results = data.get('result', [])
        if not results:
            print("No new messages found. Please send a message (e.g., 'Hello') to your bot in Telegram and run this script again.")
            return

        # Get the last message
        last_update = results[-1]
        chat_id = last_update['message']['chat']['id']
        username = last_update['message']['chat'].get('username', 'Unknown')
        print(f"\nSUCCESS! Found Chat ID:")
        print(f"Chat ID: {chat_id}")
        print(f"User: {username}")
        print("--------------------------------------------------")
        print("Copy this Chat ID into your config.yaml")
        
    except Exception as e:
        print(f"Error connecting to Telegram: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        token = sys.argv[1]
    else:
        # Try to read from config if not provided
        try:
            import yaml
            with open('config.yaml', 'r') as f:
                conf = yaml.safe_load(f)
                token = conf['telegram']['bot_token']
        except:
            token = input("Enter your Bot Token: ").strip()

    if token == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or not token:
        print("Please enter a valid Bot Token.")
    else:
        get_chat_id(token)
