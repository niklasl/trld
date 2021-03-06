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
- [ ] Serializer

### [Target Vocabulary Maps](#about-target-vocabulary-maps) _(Experimental)_
- [x] Basic RDFS & OWL
- [x] Property chains
- [x] Reified forms
- [ ] SKOS matches

## Building & Testing (& Status)

Requirements:
* Make
* For Python: Python 3.6+ (and mypy for development)
* For Java: Java 8+ (uses Gradle Wrapper)
* For JS: Node 11+ (using ES6 & ESM)

For Python, this runs mypy and the test suite:

    $ make python
    [...]

    python3 -m trld.jsonld.test [...]
    Running test suite: cache/json-ld-api/tests/expand-manifest.jsonld
    Ran 371 test cases. Passed: 366. Failed: 4. Errors: 1.
    Running test suite: cache/json-ld-api/tests/compact-manifest.jsonld
    Ran 239 test cases. Passed: 238. Failed: 1. Errors: 0.
    Running test suite: cache/json-ld-api/tests/flatten-manifest.jsonld
    Ran 55 test cases. Passed: 55. Failed: 0. Errors: 0.
    Running test suite: cache/json-ld-api/tests/fromRdf-manifest.jsonld
    Ran 51 test cases. Passed: 51. Failed: 0. Errors: 0.
    Running test suite: cache/json-ld-api/tests/toRdf-manifest.jsonld
    Ran 451 test cases. Passed: 399. Failed: 51. Errors: 1.

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

## Running

Python-based command-line usage:

    $ python3 -m trld.jsonld [-f] [-c CONTEXT] FILE

Java-based command-line usage:

    $ java -jar build/java/build/libs/trld-with-deps.jar [-f] [-c CONTEXT] FILE

JS-based command-line usage:

    $ cd build/js
    $ node -r esm lib/jsonld/cli.js [-f] [-c CONTEXT] FILE

## About Target Vocabulary Maps

This is a mapping technique for translating data using one set of
vocabularies/ontologies into another, without employing full OWL reasoning in
the process. It uses RDFS and OWL (sometimes creatively) to derive fairly
simple maps from source terms to result terms, which are then used at runtime
for a speedy translation process.

The key difference from regular OWL inference is that a _target_ vocabulary, or
an ordered array of terms or prefixes (provided as a JSON-LD context) is
defined and used when creating the mapping. The algorithm then creates a map to
these terms, from a set of known ontology assertions, ranging from basic RDFS &
OWL super-, sub- and equivalent relationships, via property chains to
properties derived from reified forms.

The resulting map is then used to translate input data, described by any terms
from the known vocabularies, into output data using the desired target
vocabulary terms.
