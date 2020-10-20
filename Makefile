python:
	python3 -m trld.jsonld.test ~/repos/github/w3c/json-ld-api/tests/expand-manifest.jsonld ~/repos/github/w3c/json-ld-api/tests/compact-manifest.jsonld 2>&1 | grep '^Ran '
	mypy trld/jsonld/

java:
	mkdir -p build/java
	python3 -m transpile.java trld/jsonld/expansion.py trld/jsonld/compaction.py -o build/java/src/main/java
	cp -R transpile/templates/java build
	(cd build/java && ./gradlew -q clean uberjar test)

js:
	python3 -m transpile.js trld/jsonld/expansion.py trld/jsonld/compaction.py -o build/js/lib
	cp -R transpile/templates/js build
	(cd build/js && npm test)
