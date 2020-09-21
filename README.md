# TRanspiler for Linked Data

TRLD is an implementation of JSON-LD algorithms. It is written in (a currently
somewhat boring and overly cast subset of) typed Python and transpiled into:
Java, ...

Requires:
* Make
* For Python: Python 3.6+
* For Java: Java 8+

Building & testing:

    $ make python java

Python-based command-line usage:

    $ python3 -m trld.jsonld [-c CONTEXT] FILE

Java-based command-line usage:

    $ java -jar build/java/build/libs/trld-with-deps.jar [-c CONTEXT] FILE
