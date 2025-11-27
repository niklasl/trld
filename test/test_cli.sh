#!/usr/bin/env bash
set -euxo pipefail

python3 -m trld test/data/examples/test-basic-data.jsonld -e
python3 -m trld test/data/examples/test-basic-data.jsonld -e -c -C

python3 -m trld test/data/examples/test-basic-data.json -e test/data/examples/test-basic-context.jsonld
python3 -m trld test/data/examples/test-basic-data.json -e test/data/examples/test-basic-context.jsonld -c

python3 -m trld test/data/examples/test-basic-data.json -e test/data/examples/test-basic-context.jsonld -c test/data/examples/test-custom-context.jsonld

python3 -m trld test/data/examples/test-custom-data.jsonld -r

python3 -m trld test/data/examples/test-denormalized.ttl -rottl
