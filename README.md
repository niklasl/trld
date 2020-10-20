# TRanspiler for Linked Data

TRLD is an implementation of JSON-LD algorithms. It is written in (a currently
somewhat boring and overly cast subset of) typed Python and transpiled into:
* Java
* Javascript

Requires:
* Make
* For Python: Python 3.6+ (and mypy for development)
* For Java: Java 8+ (uses Gradle Wrapper)
* For JS: Node 11+ (using ES6 & ESM)

## Building & Testing

To build and test everything, run:

    $ make python java js

For Python, this runs mypy and the test suite.

For the other languages, this will generate packages for each language in the
build directory.

## Running

Python-based command-line usage:

    $ python3 -m trld.jsonld [-c CONTEXT] FILE

Java-based command-line usage:

    $ java -jar build/java/build/libs/trld-with-deps.jar [-c CONTEXT] FILE

JS-based command-line usage:

    $ node -r esm lib/jsonld/cli.js [-c CONTEXT] FILE
