# TRanspiler for Linked Data

TRLD is a polyglot implementation of [JSON-LD](https://json-ld.org/)
algorithms.

It is written in Python and transpiled into:
* Java
* Javascript

The transpiler is part of the codebase and only supports the small (somewhat
boring and overly cast) subset of type-annotated Python needed to implement
these algorithms. _It is not a generic transpiler_.

## Implemented Algorithms

### [JSON-LD 1.1](https://www.w3.org/TR/json-ld11-api/)
- [x] Expansion
- [x] Compaction
- [x] Flattening
- [ ] RDF Serialization/Deserialization

## Building & Testing (& Status)

Requirements:
* Make
* For Python: Python 3.6+ (and mypy for development)
* For Java: Java 8+ (uses Gradle Wrapper)
* For JS: Node 11+ (using ES6 & ESM)

For Python, this runs mypy and the test suite:

    $ make python
    ...
    Running test suite: expand-manifest.jsonld
    Ran 369 test cases. Passed: 362. Failed: 7. Errors: 0.

    Running test suite: compact-manifest.jsonld
    Ran 239 test cases. Passed: 238. Failed: 1. Errors: 0.

    Running test suite: flatten-manifest.jsonld
    Ran 55 test cases. Passed: 55. Failed: 0. Errors: 0.

For the other languages, this will generate packages for each language in the
build directory, then run their respective test suites:

    $ make java
    ...
    545 tests completed, 19 failed

    $ make js
    ...
    1..545
    # tests 545
    # pass  538
    # fail  7

## Running

Python-based command-line usage:

    $ python3 -m trld.jsonld [-f] [-c CONTEXT] FILE

Java-based command-line usage:

    $ java -jar build/java/build/libs/trld-with-deps.jar [-f] [-c CONTEXT] FILE

JS-based command-line usage:

    $ cd build/js
    $ node -r esm lib/jsonld/cli.js [-f] [-c CONTEXT] FILE
