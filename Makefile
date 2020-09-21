python:
	python3 -m trld.jsonld.test ~/repos/github/w3c/json-ld-api/tests/expand-manifest.jsonld ~/repos/github/w3c/json-ld-api/tests/compact-manifest.jsonld 2>&1 | grep '^Ran '
	mypy trld/jsonld/

java:
	mkdir -p build/java
	cp -R transpile/templates/java build
	python3 -m transpile.java trld/jsonld/base.py trld/jsonld/context.py trld/jsonld/expansion.py trld/jsonld/invcontext.py trld/jsonld/compaction.py -o build/java/src/main/java
	(cd build/java && ./gradlew -q clean uberjar test)
