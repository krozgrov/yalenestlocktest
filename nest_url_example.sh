#!/bin/bash
# Example: Using proto_decode.py with Nest URL
# This shows how to use the general-purpose decoder with Nest's endpoint

echo "=========================================="
echo "Nest URL Example for proto_decode.py"
echo "=========================================="
echo ""
echo "This demonstrates how to use proto_decode.py with Nest:"
echo ""

# First, you need to authenticate and get an access token
# Then build the Observe request payload
# Then use proto_decode.py with the URL

echo "Step 1: Authenticate with Nest (using auth.py or nest_tool.py)"
echo "  This gives you an access_token"
echo ""
echo "Step 2: Build Observe request payload"
echo "  python -c \"from proto.nestlabs.gateway import v2_pb2; req = v2_pb2.ObserveRequest(version=2, subscribe=True); ...\" > request.bin"
echo ""
echo "Step 3: Use proto_decode.py with Nest URL:"
echo ""
echo "python proto_decode.py decode \\"
echo "  --url https://grpc-web.production.nest.com/nestlabs.gateway.v2.GatewayService/Observe \\"
echo "  --method POST \\"
echo "  --post-data request.bin \\"
echo "  --headers '{\"Authorization\": \"Basic YOUR_ACCESS_TOKEN\", \"Content-Type\": \"application/x-protobuf\", \"Accept\": \"application/x-protobuf\", \"X-Accept-Response-Streaming\": \"true\"}' \\"
echo "  --proto-path proto \\"
echo "  --message-type nest.rpc.StreamBody \\"
echo "  --format grpc-web \\"
echo "  --stream \\"
echo "  --timeout 30"
echo ""
echo "=========================================="
echo "For a complete working example, see:"
echo "  - nest_tool.py (uses the decoder internally)"
echo "  - test_nest_url.py (demonstrates URL usage)"
echo "=========================================="

