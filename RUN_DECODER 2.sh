#!/bin/bash
# Run the trait decoder

cd "$(dirname "$0")"
source .venv/bin/activate
python decode_traits.py

