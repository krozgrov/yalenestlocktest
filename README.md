An effort in prototyping and troublshooting the usage of the Google Nest grcp-web endpoint

# Setup

## Dependencies

There are 2 separate requirements.txt files. This is because the `blackboxprotobuf` package depends on an older version of `protobuf`, but since using a newer version of `protobuf` doesn't break the `blackboxprotobuf` package (and the older version breaks the rest of the scripts here) you should install `blackboxprotobuf` without dependencies.

`pip install -r requirements.txt`
`pip install -r requirements-no-deps.txt --no-deps`

If you accidentally install `blackboxprotobuf` with dependencies and the runtime gets downgraded (you will see `ImportError: cannot import name 'runtime_version'`), simply reinstall the required `protobuf` wheel explicitly: `pip install --upgrade protobuf==6.32.1`.

## Environment File

There is a template for `.env` file called `.env_template`. Simply rename or copy the `.env_template` as `.env` and fill out the 2 variables. For information on how to get the values for the ENV file, read the instructions found [here](https://github.com/chrisjshull/homebridge-nest/tree/master?tab=readme-ov-file#using-a-google-account)


# Usage

Running the `main.py` file will authenticate with Google, get your Nest access token, and then make grpc requests to retrieve and update device information managed by Google Nest.

# Known Issues

`DecodeError in StreamBody: Error parsing message with type 'nest.rpc.StreamBody'`
This error seems to be due to the incomplete `.proto` and `pb2.py` files. I believe this is probably due to the fact that these files were made from reverse engineering the Version 1 of the Nest APIs, but the "Observe" Endpoint we are making requests to is Version 2 of the APIs.

Because of this, there is a `reverse_engineering.py` that allows you to make an "Observe" request, and then utilize the `blackboxprotobuf` package to return a psuedo-proto message structure of the encoded data returned from the API. The idea is that we can take these outputs and further refine the `.proto` files, and generate new. `pb2.py` bindings for the Nest API Version 2. 
