from proto.nestlabs.gateway import v2_pb2

def GetObservePayload(traits):
  req = v2_pb2.ObserveRequest(version=2, subscribe=True)
  for trait_name in traits:
      filt = req.filter.add()
      filt.trait_type = trait_name
  return req.SerializeToString()