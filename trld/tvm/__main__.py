import json
import sys
import os
from ..jsonld.expansion import expand
from ..jsonld.compaction import compact
from .mapmaker import make_target_map
from .mapper import map_to


args = sys.argv[1:]
if len(args) < 2:
    print('Usage: python -m trld.tvm VOCAB TARGET [INFILE]', file=sys.stderr)
    sys.exit(0)

vocabfile = args.pop(0)
target = args.pop(0)
infile = args.pop(0) if args else None

if isinstance(target, str) and os.path.isfile(target):
    with open(target) as f:
        target = json.load(f)

with open(vocabfile) as f:
    vocab = json.load(f)
    vocab = expand(vocab, vocabfile)

tgm = make_target_map(vocab, target)

if not infile:
    print(json.dumps(tgm, indent=2))
else:
    with open(infile) as f:
        indata = json.load(f)
        indata = expand(indata, infile)

    outdata = map_to(tgm, indata)
    ctx = {"@context": tgm.target}
    outdata = compact(ctx, outdata) # type: ignore
    if isinstance(outdata, dict):
        outdata.update(ctx)

    print(json.dumps(outdata, indent=2))
