# TRLD

TRLD is a transpilable implementation of algorithms for working with Linked
Data as [JSON-LD](https://json-ld.org/). This includes translating to and from
various [RDF](https://www.w3.org/RDF/) syntaxes and mapping of vocabularies.

## Transpiling Linked Data Algorithms

TRLD is written in typed Python, with some extra care taken to support
[transpilation](https://en.wikipedia.org/wiki/Source-to-source_compiler). The
implementation can currently be transpiled into:

* Java
* Javascript

The transpiler is part of the codebase and only supports the small (somewhat
redundantly cast) subset of type-annotated Python needed to implement these
algorithms. _It is not a generic transpiler_.

## Transcribing Linked Data

When parsing RDF, the syntactic statements are transcribed verbatim into
JSON-LD, keeping compact forms and ordering as much as possible. Conversely,
serialization is done by writing the JSON-LD shape out as is, using the chosen
syntax.

In order to control the exact shape of this data, use the JSON-LD algorithms
for expansion, flattening and compaction.

### Serializing JSON-LD as Turtle or TriG

At this time, care must be taken to use *simple* JSON-LD contexts in order for
Turtle or TriG serialization to work. That means that, apart from prefixes and
some support for language indexes and type coercion, no advanced compaction
features of JSON-LD 1.1 will work when transcribing the data out as Turtle or
TriG. If you process such compacted data, ensure to expand it first, and
preferably re-compact it into a simpler form.

## Implemented Algorithms

### [JSON-LD 1.1](https://www.w3.org/TR/json-ld11-api/) _(W3C Spec)_
- [x] Expansion
- [x] Compaction
- [x] Flattening
- [x] RDF Serialization/Deserialization

### [N-Quads](https://www.w3.org/TR/n-quads/) _(W3C Spec)_
- [x] Parser
- [x] Serializer

### [TriG](https://www.w3.org/TR/trig/) _(W3C Spec)_
- [x] Parser
- [x] Serializer

### [Target Vocabulary Maps](https://github.com/niklasl/ldtvm#target-vocabulary-maps) _(Experimental)_
- [x] Basic RDFS & OWL
- [x] Property chains
- [x] Reified forms
- [ ] SKOS matches

## Running

Python-based command-line usage:

    $ python3 -m trld [-h] [-c CONTEXT] [-e [EXPAND_CONTEXT]] [-b BASE] [-f] \
      [-i INPUT_FORMAT] [-o OUTPUT_FORMAT] [SOURCE ...]

Java-based command-line usage:

    $ java -jar build/java/build/libs/trld-with-deps.jar [-f] [-c CONTEXT] FILE

JS-based command-line usage:

    $ cd build/js
    $ node -r esm lib/jsonld/cli.js [-f] [-c CONTEXT] FILE

## Building & Testing (& Status)

Build requirements:

* Make
* For Python: Python 3.6+ (and mypy for development)
* For Java: Java 8+ (uses Gradle Wrapper)
* For JS: Node 11+ (using ES6 & ESM)

For Python, this runs mypy and the test suite:

    $ make pytest
    [...]

    python3 -m trld.jsonld.test [...]
    Running test suite: cache/json-ld-api/tests/expand-manifest.jsonld
    Ran 371 test cases. Passed: 366. Failed: 4. Errors: 1.
    Running test suite: cache/json-ld-api/tests/compact-manifest.jsonld
    Ran 242 test cases. Passed: 239. Failed: 2. Errors: 1.
    Running test suite: cache/json-ld-api/tests/flatten-manifest.jsonld
    Ran 55 test cases. Passed: 55. Failed: 0. Errors: 0.
    Running test suite: cache/json-ld-api/tests/fromRdf-manifest.jsonld
    Ran 51 test cases. Passed: 51. Failed: 0. Errors: 0.
    Running test suite: cache/json-ld-api/tests/toRdf-manifest.jsonld
    Ran 451 test cases. Passed: 400. Failed: 50. Errors: 1.

    python3 -m trld.tvm.test
    Running [...]: OK

    python3 -m trld.trig.test [...]
    Ran 335 tests. Passed 301, failed 34

For the other languages, this will generate packages for each language in the
build directory, then run their respective test suites:

    $ make java
    [...]
    java -cp build/java/build/libs/trld-with-deps.jar trld.jsonld.TestRunner [...]
    Ran 371 test cases. Passed: 329. Failed: 15. Errors: 27.

    java -cp build/java/build/libs/trld-with-deps.jar trld.trig.Test [...]
    Ran 335 tests. Passed 252, failed 83

    $ make js
    [...]
    1..547
    # tests 547
    # pass  542
    # fail  5

    [...] node [...] lib/trig/test.js [...]
    Ran 335 tests. Passed 270, failed 65

