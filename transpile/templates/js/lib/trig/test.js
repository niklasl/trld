'use strict'

import { jsonEncodeCanonical } from '../platform/common.js'
import { Input } from '../platform/io.js'
import { CONTEXT, GRAPH, ID, TYPE, LIST } from '../jsonld/base.js'
import { expand } from '../jsonld/expansion.js'
import { compact } from '../jsonld/compaction.js'
import { flatten } from '../jsonld/flattening.js'
import { toRdfDataset, toJsonld } from '../jsonld/rdf.js'
import { parse as nq_parse } from '../nq/parser.js'
import { parse } from './parser.js'

export async function *readManifest (manifestPath) {
  let data = await parse(new Input(manifestPath.toString()))
  let index = Array.from(data[GRAPH]).filter((node) => ID in node).reduce((d, node) => { d[node[ID]] = node; return d }, {})
  let testentries = index[""]["mf:entries"][LIST]
  for (let testentry of testentries) {
    let tnode = index[testentry[ID]]
    let ttype = ("rdf:type" in tnode ? tnode["rdf:type"][ID] : tnode[TYPE])
    let taction = tnode["mf:action"][ID]
    let tresult = ("mf:result" in tnode ? tnode["mf:result"][ID] : null)
    yield [ttype, taction, tresult]
  }
}

export async function runTests (testSuiteDir) {
  let i = 0
  let failed = 0
  let passed = 0
  let manifest = readManifest(testSuiteDir + '/' + "manifest.ttl")
  for await (let [ttype, taction, tresult] of manifest) {
    i += 1
    let trigPath = testSuiteDir + '/' + taction
    let negative = ttype == "rdft:TestTrigNegativeSyntax"
    let inp = new Input(trigPath.toString())
    try {
      let result = await parse(inp)
      // assert result != null : null
      if (negative) {
        console.log("SHOULD FAIL on " + trigPath + " (a " + ttype + ")")
        failed += 1
      } else if (tresult) {
        let nqPath = testSuiteDir + '/' + tresult
        let expected
        try {
          expected = await nq_parse(new Input(nqPath))
        } catch (e) {
          console.log("Error parsing NQuads " + nqPath)
          throw e
        }
        let baseUri = "http://www.w3.org/2013/TriGTests/"
        let context = result[CONTEXT]
        let resultrepr = datarepr(result, context, baseUri + trigPath.name)
        let expectedrepr = datarepr(expected, context, baseUri + nqPath.name)
        if (resultrepr != expectedrepr) {
          console.log("FAILED COMPARISON for " + trigPath + " (" + ttype + "). Got:")
          console.log("\t" + resultrepr);
          console.log("Expected from " + nqPath + ":")
          console.log("\t" + expectedrepr)
          console.log("")
          failed += 1
        } else {
          passed += 1
        }
      } else {
        passed += 1
      }
    } catch (e) {
      if (negative) {
        passed += 1
      } else {
        console.log("FAILED on " + trigPath + " (a " + ttype + "):")
        console.log(e)
        failed += 1
      }
    }
  }
  console.log("Ran " + i + " tests. Passed " + passed + ", failed " + failed)
}

export function datarepr (data, context, baseUri) {
  data = expand(data, baseUri)
  data = flatten(data)
  let dataset = toRdfDataset(data)
  data = toJsonld(dataset)
  data = compact(context, data, "", true)
  return jsonEncodeCanonical(data)
}

export default async function main () {
  let args = process.argv.slice(2)
  runTests(args[0])
}

if (typeof require !== 'undefined' && require.main === module) main()
