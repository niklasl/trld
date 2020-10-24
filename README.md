# TRanspiler for Linked Data

TRLD is an implementation of [JSON-LD](https://json-ld.org/) algorithms:

- [x] Expansion
- [x] Compaction
- [ ] Flattening
- [ ] RDF Serialization/Deserialization

It is written in Python and transpiled into:
* Java
* Javascript

The transpiler is part of the project and only supports the small (somewhat
boring and overly cast) subset of type-annotated Python needed to implement
these algorithms. _It is not a generic transpiler_.

## Building & Testing (& Status)

Requirements:
* Make
* For Python: Python 3.6+ (and mypy for development)
* For Java: Java 8+ (uses Gradle Wrapper)
* For JS: Node 11+ (using ES6 & ESM)

For Python, this runs mypy and the test suite:

    $ make python
    ...
    Ran 369 test cases. Passed: 343. Failed: 26. Errors: 0.
    Ran 239 test cases. Passed: 238. Failed: 1. Errors: 0.

For the other languages, this will generate packages for each language in the
build directory, then run their respective test suites:

    $ make java
    ...
    495 tests completed, 33 failed

    $ make js
    ...
    1..495
    # tests 495
    # pass  472
    # fail  23

## Running

Python-based command-line usage:

    $ python3 -m trld.jsonld [-c CONTEXT] FILE

Java-based command-line usage:

    $ java -jar build/java/build/libs/trld-with-deps.jar [-c CONTEXT] FILE

JS-based command-line usage:

    $ cd build/js
    $ node -r esm lib/jsonld/cli.js [-c CONTEXT] FILE
