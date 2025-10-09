import blackboxprotobuf as bbp

from auth import GetSessionWithAuth
from proto_utils import GetObservePayload
from proto import rootv2_pb2 as root

from const import (
  USER_AGENT_STRING,
  ENDPOINT_OBSERVE,
  URL_PROTOBUF,
  PRODUCTION_HOSTNAME
)
# from protobuf_handler import NestProtobufHandler

# Get Requests Session and all the information needed for authenticating with Nest 
session, access_token, user_id, transport_url = GetSessionWithAuth()
print("Got session and access token")

# Payload for getting data from the Nest Observe Endpoint
payload = GetObservePayload([
  "nest.trait.user.UserInfoTrait",
  "nest.trait.structure.StructureInfoTrait"
])

headers = {
  'Accept-Encoding': 'gzip, deflate, br, zstd',
  'Content-Type': 'application/x-protobuf',
  'User-Agent': USER_AGENT_STRING,
  'X-Accept-Response-Streaming': 'true',
  'Accept': 'application/x-protobuf',
  'referer': 'https://home.nest.com/',
  'origin': 'https://home.nest.com',
  'X-Accept-Content-Transfer-Encoding': 'binary',
  'Authorization': 'Basic ' + access_token
}
print("Headers and payload ready, sending observe request")
observe_response = session.post(f'{URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME['grpc_hostname'])}{ENDPOINT_OBSERVE}', headers=headers, data=payload, stream=True)

locks_data = {}
for chunk in observe_response.iter_content(chunk_size=None):
  if chunk:
    message, typedef = bbp.protobuf_to_json(chunk)
    print("############ Raw Message ############")
    print(message)
    print("####################################")
    streambody = root.StreamBody()
    streambody.ParseFromString(chunk)
    print("############ Parsed Message ############")
    print(streambody.message)
    print("########################################")
    print("########################################")