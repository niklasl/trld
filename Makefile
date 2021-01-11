trld_modules = trld/jsonld/expansion.py trld/jsonld/compaction.py trld/jsonld/flattening.py trld/jsonld/rdf.py trld/nq/parser.py trld/nq/serializer.py trld/tvm/mapmaker.py trld/tvm/mapper.py
jsonld_api_dir = ~/repos/github/w3c/json-ld-api

build:
	mkdir -p $(shell readlink -f build)

python:
	python3 -m trld.jsonld.test $(jsonld_api_dir)/tests/expand-manifest.jsonld $(jsonld_api_dir)/tests/compact-manifest.jsonld $(jsonld_api_dir)/tests/flatten-manifest.jsonld $(jsonld_api_dir)/tests/fromRdf-manifest.jsonld $(jsonld_api_dir)/tests/toRdf-manifest.jsonld 2>&1 | grep '^Running test suite\|^Ran '
	python3 -m trld.tvm.test
	mypy trld/jsonld/

java: build
	mkdir -p build/java
	python3 -m transpile.java $(trld_modules) -o build/java/src/main/java
	cp -R transpile/templates/java build
	(cd build/java && ./gradlew -q clean uberjar test)

js: build/js/node_modules
	python3 -m transpile.js $(trld_modules) -o build/js/lib
	cp -R transpile/templates/js build
	(cd build/js && npm test)

build/js/node_modules: build
	mkdir -p build/js
	(cd build/js && npm i)
