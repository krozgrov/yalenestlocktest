import json
import blackboxprotobuf as bbp

from auth import GetSessionWithAuth
from proto_utils import GetObservePayload, SendGRPCRequest, ParseStreamBody
from const import (
  ENDPOINT_OBSERVE,
)

DEBUG = True


# Get Requests Session and all the information needed for authenticating with Nest 
session, access_token, user_id, transport_url = GetSessionWithAuth()
print("Got session and access token")

# Payload for getting data from the Nest Observe Endpoint
payload = GetObservePayload([
  "nest.trait.user.UserInfoTrait",
  "nest.trait.structure.StructureInfoTrait"
])

# Send the observe request to the Nest API
observe_response = SendGRPCRequest(session, ENDPOINT_OBSERVE, access_token, payload)

# Iterate Response and parse each protobuf message
for chunk in observe_response.iter_content(chunk_size=None):
  if chunk:
    if DEBUG == True:
      message, typedef = bbp.protobuf_to_json(chunk)
      print("############ Raw Message ############")
      print(message)
      print("####################################")
    nest_data = ParseStreamBody(chunk)
    print("############ Parsed Message ############")
    print(json.dumps(nest_data, indent=2))
    print("########################################")
    print("########################################")