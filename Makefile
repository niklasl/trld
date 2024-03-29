trld_modules = trld/jsonld/expansion.py trld/jsonld/compaction.py trld/jsonld/flattening.py trld/jsonld/rdf.py trld/jsonld/testbase.py trld/nq/parser.py trld/nq/serializer.py trld/trig/parser.py trld/trig/serializer.py trld/tvm/mapmaker.py trld/tvm/mapper.py -I trld/builtins.py trld/platform/*.py

mkdir = python -c 'import sys, pathlib; pathlib.Path(sys.argv[1]).resolve().mkdir(parents=1, exist_ok=1)'

clean:
	rm -rf build/*

build:
	$(mkdir) build

cache:
	$(mkdir) cache

dist:
	$(mkdir) dist

cache/json-ld-api: | cache
	git clone https://github.com/w3c/json-ld-api.git cache/json-ld-api

cache/trig-tests.tar.gz: | cache
	curl -o $@ https://www.w3.org/2013/TrigTests/TESTS.tar.gz

cache/trig-tests: cache/trig-tests.tar.gz
	mkdir -p $@
	tar -xzf $^ -C $@

pytest: | cache/json-ld-api cache/trig-tests
	mypy trld/
	find trld -name '*.py' | xargs grep -l '^\s*>>> ' | sed 's/\.py\>//; s!/!.!g'| xargs -n1 python3 -m
	python3 -m trld.jsonld.test cache/json-ld-api/tests/expand-manifest.jsonld cache/json-ld-api/tests/compact-manifest.jsonld cache/json-ld-api/tests/flatten-manifest.jsonld cache/json-ld-api/tests/fromRdf-manifest.jsonld cache/json-ld-api/tests/toRdf-manifest.jsonld 2>&1 | grep '^Running test suite\|^Ran '
	python3 -m trld.tvm.test
	python3 -m trld.trig.test | grep '^Ran '
	python3 -m trld.trig.test_serializer | grep '^Examined '
	python3 -m trld test/data/examples/misc.trig | python3 -m trld -i jsonld -o trig | python3 -m trld -i trig > /dev/null
	python3 -m trld test/data/newlinestrings.jsonld -o ttl | python3 -m trld -i ttl -o ttl | python3 -m trld -i ttl > /dev/null

pydev: dev-requirements.txt
	python -c 'import sys; assert sys.prefix != sys.base_prefix, "Not in a venv"'
	pip install -r dev-requirements.txt

pypkg: build dist pydev pytest
	python3 -m build

javatr: build | cache/json-ld-api cache/trig-tests
	mkdir -p build/java
	python3 -m transpile.java $(TRFLAGS) $(trld_modules) -o build/java/src/main/java
	cp -R transpile/templates/java build

java: javatr
	(cd build/java && ./gradlew -q clean uberjar test)
	java -cp build/java/build/libs/trld-with-deps.jar trld.jsonld.TestRunner cache/json-ld-api/tests 2>&1 | grep '^Ran '
	java -cp build/java/build/libs/trld-with-deps.jar trld.trig.Test cache/trig-tests 2>&1 | grep '^Ran '

jar: javatr
	(cd build/java && ./gradlew -q test jar)

jstr: build/js/node_modules
	python3 -m transpile.js $(TRFLAGS) $(trld_modules) -o build/js/lib
	cp -R transpile/templates/js build

js: jstr
	(cd build/js && TRLD_JSONLD_TESTDIR=$(shell pwd)/cache/json-ld-api/tests npm test || true)
	(cd build/js && node -r esm lib/trig/test.js $(shell pwd)/cache/trig-tests) | grep '^Ran'

build/js/node_modules: build/js/package.json
	(cd build/js && npm i)

build/js/package.json: build
	cp -R transpile/templates/js build
