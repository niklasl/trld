import tape from 'tape'
import os from 'os'

import { expand } from '../lib/jsonld/expansion.js'
import { compact } from '../lib/jsonld/compaction.js'
import { loadJson } from '../lib/jsonld/common'

const TESTSUITE_DIR = `file://${os.homedir()}/repos/github/w3c/json-ld-api/tests/`
const TESTSUITE_BASE_URL = 'https://w3c.github.io/json-ld-api/tests'

function testCaseRunner(category) {
  let manifestFile = `${TESTSUITE_DIR }${category}-manifest.jsonld`
  let manifest = loadJson(manifestFile);
  for (let tc of manifest.sequence) {
    if (tc["@type"].indexOf("jld:PositiveEvaluationTest") === -1) {
      return
    }
    let label = `${category} ${tc["@id"]} - ${tc.purpose}`
    tape.test(label, t => {
      let src = TESTSUITE_DIR + tc.input
      let url = TESTSUITE_BASE_URL + tc.input
      let options = tc.option || {}
      let baseUri = options.base || url

      let sourceData = loadJson(src)

      let contextData
      if (tc.context) {
        let contextSrc = TESTSUITE_DIR + tc.context
        contextData = loadJson(contextSrc)
        sourceData = expand(sourceData, baseUri)
      }

      let expectedSrc = TESTSUITE_DIR + tc.expect
      let expectedData = loadJson(expectedSrc)
      if ('@context' in expectedData) {
        delete expectedData['@context']
      }

      let resultData
      if (contextData) {

        let compactArrays = options.compactArrays
        if (compactArrays === void(0)) compactArrays = true
        resultData = compact(contextData, sourceData, baseUri, compactArrays)
      } else {
        resultData = expand(sourceData, baseUri)
      }

      t.deepEqual(resultData, expectedData)
      t.end()
    })
  }
}

testCaseRunner('expand')
testCaseRunner('compact')
