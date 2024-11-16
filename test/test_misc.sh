#!/bin/bash

python3 -m trld test/data/examples/misc.trig | python3 -m trld -i jsonld -o trig | python3 -m trld -i trig > /dev/null

python3 -m trld test/data/newlinestrings.jsonld -o ttl | python3 -m trld -i ttl -o ttl | python3 -m trld -i ttl > /dev/null

python3 test/trig/test_compact_jsonld_to_trig.py
