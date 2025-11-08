import argparse
import base64
import json
import uuid
from dotenv import load_dotenv
import os
import asyncio
import requests
from google.protobuf import any_pb2
from proto.nestlabs.gateway import v1_pb2
from proto.nestlabs.gateway import v2_pb2
from proto.weave.trait import security_pb2 as weave_security_pb2
from protobuf_handler import NestProtobufHandler
from const import (
  API_TIMEOUT_SECONDS,
  USER_AGENT_STRING,
  ENDPOINT_OBSERVE,
  ENDPOINT_SENDCOMMAND,
  URL_PROTOBUF,
  PRODUCTION_HOSTNAME
)
import requests

def parse_args():
  parser = argparse.ArgumentParser(description="Inspect Yale lock state and optionally send a lock/unlock command.")
  parser.add_argument(
    "--action",
    choices=["status", "lock", "unlock"],
    default="status",
    help="Post-observe action. 'status' only prints state; 'lock' or 'unlock' sends a command."
  )
  parser.add_argument(
    "--device-id",
    help="Lock device id to control. Defaults to the first discovered Yale lock."
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Build and display the command without sending it to Nest."
  )
  return parser.parse_args()

args = parse_args()

load_dotenv()

ISSUE_TOKEN = os.environ.get("ISSUE_TOKEN")
COOKIES = os.environ.get("COOKIES")


def _normalize_base(url: str | None) -> str | None:
  if not url:
    return None
  return url.rstrip("/")


def _transport_candidates(session_base: str | None) -> list[str]:
  candidates = []
  normalized_session = _normalize_base(session_base)
  if normalized_session:
    candidates.append(normalized_session)
  default = _normalize_base(URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"]))
  if default and default not in candidates:
    candidates.append(default)
  return candidates

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
headers_observe = {
  'Accept-Encoding': 'gzip, deflate, br, zstd',
  'Content-Type': 'application/x-protobuf',
  'User-Agent': USER_AGENT_STRING,
  'X-Accept-Response-Streaming': 'true',
  'Accept': 'application/x-protobuf',
  # 'x-nl-webapp-version': 'NlAppSDKVersion/8.15.0 NlSchemaVersion/2.1.20-87-gce5742894',
  'referer': 'https://home.nest.com/',
  'origin': 'https://home.nest.com',
  'X-Accept-Content-Transfer-Encoding': 'binary',
  'Authorization': 'Basic ' + access_token
}

# Build Observe Request Payload
req = v2_pb2.ObserveRequest(version=2, subscribe=True)
trait_names = [
  "nest.trait.user.UserInfoTrait",
  "nest.trait.structure.StructureInfoTrait",
  "weave.trait.security.BoltLockTrait",
  "weave.trait.security.BoltLockSettingsTrait",
  "weave.trait.security.BoltLockCapabilitiesTrait",
  "weave.trait.security.PincodeInputTrait",
  "weave.trait.security.TamperTrait",
  # HomeKit-relevant traits
  "weave.trait.description.DeviceIdentityTrait",  # Serial, firmware, model
  "weave.trait.power.BatteryPowerSourceTrait",    # Battery level, status
]
for trait_name in trait_names:
    filt = req.filter.add()
    filt.trait_type = trait_name
payload_observe = req.SerializeToString()

locks_data = {}
observe_base = None
observe_response = None
for base_url in _transport_candidates(transport_url):
  target_url = f"{base_url}{ENDPOINT_OBSERVE}"
  try:
    print(f"[main] Sending Observe request to {target_url}")
    response = session.post(target_url, headers=headers_observe, data=payload_observe, stream=True, timeout=(API_TIMEOUT_SECONDS, API_TIMEOUT_SECONDS))
    response.raise_for_status()
    observe_response = response
    observe_base = base_url
    break
  except requests.HTTPError as err:
    status = err.response.status_code if err.response else "unknown"
    print(f"[main] Observe failed for {target_url} (status {status}): {err}")
  except Exception as err:
    print(f"[main] Observe error for {target_url}: {err}")

if observe_response is None:
  session.close()
  raise SystemExit("Failed to open Observe stream against all transport endpoints.")

handler = NestProtobufHandler()
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
print()
print(json.dumps(locks_data, indent=2))
print ("################################\n")

if args.action == "status":
  session.close()
  raise SystemExit(0)

user_id = locks_data.get("user_id", None)
structure_id = locks_data.get("structure_id", None)
locks = locks_data.get("yale", {})

device_id = None
if args.device_id:
  lock_info = locks.get(args.device_id)
  if not lock_info:
    available = ", ".join(locks.keys()) or "none"
    session.close()
    raise SystemExit(f"Requested device_id '{args.device_id}' not found. Available locks: {available}")
  device_id = lock_info.get("device_id") or args.device_id
else:
  for lock_id, lock_info in locks.items():
    if lock_info.get("device_id"):
      device_id = lock_info["device_id"]
      break

if not device_id:
  session.close()
  raise SystemExit("No Yale lock device_id discovered; nothing to control.")


# Send an unlock command to a lock
if args.action == "unlock":
  state = weave_security_pb2.BoltLockTrait.BOLT_STATE_RETRACTED
elif args.action == "lock":
  state = weave_security_pb2.BoltLockTrait.BOLT_STATE_EXTENDED
else:
  session.close()
  raise SystemExit(f"Unsupported action {args.action!r}.")

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

print(f"###### COMMAND FOR {device_id} ({args.action}) ######")
print(base64.b64encode(command["command"]["value"]))
print(request)
print("###################################\n")
if args.dry_run:
  print("Dry-run enabled; skipping command dispatch.")
  session.close()
  raise SystemExit(0)

if structure_id:
  headers["X-Nest-Structure-Id"] = structure_id

command_base_candidates = []
if observe_base:
  command_base_candidates.append(observe_base)
command_base_candidates.extend(
  base for base in _transport_candidates(transport_url)
  if base not in command_base_candidates
)

try:
  response_message = None
  last_error = None
  for base_url in command_base_candidates:
    api_url = f"{base_url}{ENDPOINT_SENDCOMMAND}"
    try:
      print(f"[main] Posting command to {api_url}")
      command_response = session.post(api_url, headers=headers, data=encoded_data, timeout=API_TIMEOUT_SECONDS)
      print(f"[main] Command response status: {command_response.status_code}")
      if command_response.status_code != 200:
        print(f"[main] Response body: {command_response.text}")
        command_response.raise_for_status()
      response_message = v1_pb2.ResourceCommandResponseFromAPI()
      response_message.ParseFromString(command_response.content)
      break
    except Exception as err:
      last_error = err
      print(f"[main] Command attempt failed for {api_url}: {err}")
  if response_message is None:
    raise last_error or RuntimeError("Command failed for all transport endpoints.")

  print("######### COMMAND RESPONSE #########")
  print(response_message)
  print("###################################")
except Exception as e:
  print(f"Command failed for {device_id}: {e}")
finally:
  session.close()
