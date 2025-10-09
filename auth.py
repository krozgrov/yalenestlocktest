from dotenv import load_dotenv
import os
import requests
from const import (
  API_TIMEOUT_SECONDS,
  USER_AGENT_STRING,
  URL_PROTOBUF,
)

load_dotenv()

ISSUE_TOKEN = os.environ.get("ISSUE_TOKEN")
COOKIES = os.environ.get("COOKIES")

def GetSessionWithAuth():
  # Google Access Token
  headers = {
    'Sec-Fetch-Mode': 'cors',
    'X-Requested-With': 'XmlHttpRequest',
    'Referer': 'https://accounts.google.com/o/oauth2/iframe',
    'cookie': COOKIES,
    'User-Agent': USER_AGENT_STRING,
    'timeout': f"{API_TIMEOUT_SECONDS}",
  }
  response = requests.request("GET", ISSUE_TOKEN, headers=headers)
  google_access_token = response.json().get("access_token")
  print(response.status_code, google_access_token, response.text)
  session = requests.Session()

  # Exchange Google Access Token for Nest JWT
  nest_url = "https://nestauthproxyservice-pa.googleapis.com/v1/issue_jwt"
  nest_headers = {
    'Authorization': f'Bearer {google_access_token}',
    'User-Agent': USER_AGENT_STRING,
    'Referer': URL_PROTOBUF,
    'timeout': f"{API_TIMEOUT_SECONDS}"
  }
  nest_response = session.request("POST", nest_url, headers=nest_headers, json={
    "embed_google_oauth_access_token": "true",
    "expire_after": "3600s",
    "google_oauth_access_token": google_access_token,
    "policy_id": "authproxy-oauth-policy"
  })
  print(nest_response.status_code)
  nest_data = nest_response.json()
  access_token = nest_data.get("jwt")

  # Use Nest JWT to create session and get user ID and transport URL
  session_url = "https://home.nest.com/session"
  session_headers = {
    'User-Agent': USER_AGENT_STRING,
    'Authorization': f'Basic {access_token}',
    'cookie': f'G_ENABLED_IDPS=google; eu_cookie_accepted=1; viewer-volume=0.5; cztoken={access_token}',
    'timeout': f"{API_TIMEOUT_SECONDS}"
  }
  session_response = session.request("GET", session_url, headers=session_headers)
  print(session_response.status_code)
  session_data = session_response.json()
  print(session_data)
  access_token = session_data.get("access_token")
  user_id = session_data.get("userid")
  transport_url = session_data.get("urls").get("transport_url") 
  return session, access_token, user_id, transport_url
