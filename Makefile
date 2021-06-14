trld_modules = trld/jsonld/expansion.py trld/jsonld/compaction.py trld/jsonld/flattening.py trld/jsonld/rdf.py trld/jsonld/testcase.py trld/nq/parser.py trld/nq/serializer.py trld/tvm/mapmaker.py trld/tvm/mapper.py -I trld/common.py

clean:
	rm -rf build/*

build:
	mkdir -p $(shell readlink -f build)

cache:
	mkdir -p $(shell readlink -f cache)

cache/json-ld-api: | cache
	git clone https://github.com/w3c/json-ld-api.git cache/json-ld-api

python: | cache/json-ld-api
	mypy trld/jsonld/
	python3 -m trld.jsonld.test cache/json-ld-api/tests/expand-manifest.jsonld cache/json-ld-api/tests/compact-manifest.jsonld cache/json-ld-api/tests/flatten-manifest.jsonld cache/json-ld-api/tests/fromRdf-manifest.jsonld cache/json-ld-api/tests/toRdf-manifest.jsonld 2>&1 | grep '^Running test suite\|^Ran '
	python3 -m trld.tvm.test

java: build | cache/json-ld-api
	mkdir -p build/java
	python3 -m transpile.java $(trld_modules) -o build/java/src/main/java
	cp -R transpile/templates/java build
	(cd build/java && ./gradlew -q clean uberjar test)
	java -cp build/java/build/libs/trld-with-deps.jar trld.jsonld.TestRunner cache/json-ld-api/tests 2>&1 | grep '^Ran '

js: build/js/node_modules
	python3 -m transpile.js $(trld_modules) -o build/js/lib
	cp -R transpile/templates/js build
	(cd build/js && TRLD_JSONLD_TESTDIR=$(shell pwd)/cache/json-ld-api/tests npm test || true)

build/js/node_modules: build/js/package.json
	(cd build/js && npm i)

build/js/package.json: build
	cp -R transpile/templates/js build
