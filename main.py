from dotenv import load_dotenv
import os
import asyncio
import json
import uuid
import requests
from proto.nestlabs.gateway import v1_pb2
from google.protobuf import any_pb2
from proto.weave.trait import security_pb2 as weave_security_pb2
from protobuf_manager import _read_protobuf as read_protobuf
from protobuf_handler import NestProtobufHandler
from const import (
  API_TIMEOUT_SECONDS,
  USER_AGENT_STRING,
  ENDPOINT_OBSERVE,
  ENDPOINT_SENDCOMMAND,
  URL_PROTOBUF,
  PRODUCTION_HOSTNAME
)

load_dotenv()

REQUEST_URL = os.environ.get("REQUEST_URL")
COOKIES = os.environ.get("COOKIES")

# Google Access Token
headers = {
  'Sec-Fetch-Mode': 'cors',
  'X-Requested-With': 'XmlHttpRequest',
  'Referer': 'https://accounts.google.com/o/oauth2/iframe',
  'cookie': COOKIES,
  'User-Agent': USER_AGENT_STRING,
  'timeout': f"{API_TIMEOUT_SECONDS}",
}
response = requests.request("GET", REQUEST_URL, headers=headers)
response_header_cookies = response.headers.get("Set-Cookie")
google_access_token = response.json().get("access_token")
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
session_data = session_response.json()
access_token = session_data.get("access_token")
user_id = session_data.get("userid")
transport_url = session_data.get("urls").get("transport_url") 


# Get Lock data from Observe Endpoint
payload_observe = read_protobuf("proto/ObserveTraits.bin")
headers_observe = {
  'Content-Type': 'application/x-protobuf',
  'User-Agent': USER_AGENT_STRING,
  'X-Accept-Response-Streaming': 'true',
  'Accept': 'application/x-protobuf',
  'x-nl-webapp-version': 'NlAppSDKVersion/8.15.0 NlSchemaVersion/2.1.20-87-gce5742894',
  'referer': 'https://home.nest.com/',
  'origin': 'https://home.nest.com',
  'X-Accept-Content-Transfer-Encoding': 'binary',
  'Authorization': 'Basic ' + access_token
}

handler = NestProtobufHandler()

locks_data = {}
observe_response = session.post(f'{URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME['grpc_hostname'])}{ENDPOINT_OBSERVE}', headers=headers_observe, data=payload_observe, stream=True)
for chunk in observe_response.iter_content(chunk_size=None):
  if chunk:
    async def process_chunk(locks_data):
      new_data = await handler._process_message(chunk)
      locks_data.update(new_data)
    asyncio.run(process_chunk(locks_data))
  user_id = locks_data.get("user_id", None)
  structure_id = locks_data.get("structure_id", None)
  if user_id and structure_id:
    observe_response.close()
    break

print ("######### OBSERVE DATA #########")
print(json.dumps(locks_data, indent=2))
print ("################################\n")

user_id = locks_data.get("user_id", None)
structure_id = locks_data.get("structure_id", None)
for lock_id, lock_info in locks_data.get("yale", {}).items():
  if lock_info.get("device_id"):
    device_id = lock_info["device_id"]
    break


# Send an unlock command to a lock
state = weave_security_pb2.BoltLockTrait.BOLT_STATE_RETRACTED
request = weave_security_pb2.BoltLockTrait.BoltLockChangeRequest()
request.state = state
request.boltLockActor.method = weave_security_pb2.BoltLockTrait.BOLT_LOCK_ACTOR_METHOD_REMOTE_USER_EXPLICIT
request.boltLockActor.originator.resourceId = str(user_id)
command = {
  "traitLabel": "bolt_lock",
  "command": {
    "type_url": "type.nestlabs.com/weave.trait.security.BoltLockTrait.BoltLockChangeRequest",
    "value": request.SerializeToString(),
  }
}

request_id = str(uuid.uuid4())
headers = {
  "Authorization": f"Basic {access_token}",
  "Content-Type": "application/x-protobuf",
  "User-Agent": USER_AGENT_STRING,
  "X-Accept-Content-Transfer-Encoding": "binary",
  "X-Accept-Response-Streaming": "true",
  # "referer": "https://home.nest.com/",
  # "origin": "https://home.nest.com",
  # "x-nl-webapp-version": "NlAppSDKVersion/8.15.0 NlSchemaVersion/2.1.20-87-gce5742894",
  "request-id": request_id,
}

# Always include a structure_id header, defaulting to the fetched one
# effective_structure_id = structure_id
# if effective_structure_id:
#     headers["X-Nest-Structure-Id"] = effective_structure_id
#     print(f"[nest_yale] Using structure_id: {effective_structure_id}")

api_url = f"{URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME['grpc_hostname'])}{ENDPOINT_SENDCOMMAND}"

cmd_any = any_pb2.Any()
cmd_any.type_url = command["command"]["type_url"]
cmd_any.value = command["command"]["value"] if isinstance(command["command"]["value"], bytes) else command["command"]["value"].SerializeToString()

resource_command = v1_pb2.ResourceCommand()
resource_command.command.CopyFrom(cmd_any)
resource_command.traitLabel = command["traitLabel"]

request = v1_pb2.ResourceCommandRequest()
request.resourceCommands.extend([resource_command])
request.resourceRequest.resourceId = device_id
request.resourceRequest.requestId = request_id
encoded_data = request.SerializeToString()

print(f"###### COMMAND FOR {device_id} ######")
print(request)
print("###################################\n")
try:
  response = v1_pb2.ResourceCommandResponseFromAPI()
  command_response = session.post(api_url, headers=headers, data=encoded_data)
  response.ParseFromString(command_response.content)
  print("######### COMMAND RESPONSE #########")
  print(response)
  print("###################################")
except Exception as e:
  print(f"Command failed for {device_id}: {e}")