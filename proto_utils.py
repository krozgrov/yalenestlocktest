from google.protobuf import json_format, descriptor_database, descriptor_pool
from google.protobuf.descriptor_pb2 import FileDescriptorProto
import json
import importlib

from proto.nestlabs.gateway import v2_pb2
from proto.nest import rpc_pb2 as rpc

from const import (
  USER_AGENT_STRING,
  URL_PROTOBUF,
  PRODUCTION_HOSTNAME
)

# Loads all pb2 files into a descriptor pool for use in json_format
proto_db = descriptor_database.DescriptorDatabase()
proto_pool = descriptor_pool.DescriptorPool(proto_db)
import os
for root, dirs, files in os.walk('proto'):
  for file in files:
    if file.endswith('pb2.py') and not file.startswith('__'):
      module_name = os.path.splitext(os.path.join(root, file))[0].replace(os.sep, '.')

      desc = getattr(importlib.import_module(module_name), "DESCRIPTOR")
      serialized_desc = desc.serialized_pb
      desc = FileDescriptorProto()
      desc.ParseFromString(serialized_desc)
      print(f"Adding {module_name} to descriptor pool")
      proto_db.Add(desc)

def GetObservePayload(traits):
  req = v2_pb2.ObserveRequest(version=2, subscribe=True)
  for trait_name in traits:
    filt = req.filter.add()
    filt.trait_type = trait_name
  return req.SerializeToString()

def SendGRPCRequest(session, url, access_token, payload):
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
  observe_response = session.post(f'{URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME['grpc_hostname'])}{url}', headers=headers, data=payload, stream=True)
  return observe_response

    

def ParseStreamBody(data):
  try:
    streambody = rpc.StreamBody()
    streambody.ParseFromString(data)
    json_string = json_format.MessageToJson(streambody, descriptor_pool=proto_pool)
    json_data = json.loads(json_string)
    return json_data
  except Exception as e:
    print(f"Error parsing stream body: {e}")
    return {}