import requests

url = "http://localhost:8000/api/v1/auth/login"
data = {
    "username": "gupta.rahulg25@gmail.com",
    "password": "password"  # Assuming 'password' is a common test password, or we can check the db
}
response = requests.post(url, data=data)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
