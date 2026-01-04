import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive']

def main():
    """Shows basic usage of the Drive v3 API.
    Prints the names and ids of the first 10 files the user has access to.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Check for credentials.json which is downloadable from Cloud Console (OAuth Client ID)
            if not os.path.exists('credentials.json'):
                print("❌ Error: 'credentials.json' not found!")
                print("1. Go to Google Cloud Console > APIs & Services > Credentials")
                print("2. Create Credentials > OAuth Client ID > Desktop App")
                print("3. Download JSON and rename it to 'credentials.json'")
                print("4. Place it in this folder and run script again.")
                return

            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            print("✅ Success! 'token.json' created.")
            print("👉 Upload this 'token.json' file to your Render server (e.g. /etc/secrets/token.json)")

if __name__ == '__main__':
    main()
