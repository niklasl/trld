import tape from 'tape'
import os from 'os'

import { expand } from '../lib/jsonld/expansion.js'
import { compact } from '../lib/jsonld/compaction.js'
import * as common from '../lib/jsonld/common'

const TESTSUITE_DIR = `file://${os.homedir()}/repos/github/w3c/json-ld-api/tests/`
const TESTSUITE_BASE_URL = 'https://w3c.github.io/json-ld-api/tests/'

let loadJson = common.loadJson
function loadLocalJson(url) {
    return loadJson(url.replace(TESTSUITE_BASE_URL, TESTSUITE_DIR))
}
common.loadJson = loadLocalJson

function testCaseRunner(category) {
  let manifestFile = `${TESTSUITE_DIR}${category}-manifest.jsonld`
  let manifest = common.loadJson(manifestFile);
  for (let tc of manifest.sequence) {
    if (tc['@type'].indexOf('jld:PositiveEvaluationTest') === -1) {
      continue
    }
    let label = `${category} ${tc['@id']} - ${tc.purpose}`
    tape.test(label, t => {
      let src = TESTSUITE_DIR + tc.input
      let url = TESTSUITE_BASE_URL + tc.input
      let options = tc.option || {}
      let baseUri = options.base || url

      let ordered = true

      let sourceData = common.loadJson(src)

      let contextData
      if (tc.context) {
        let contextSrc = TESTSUITE_DIR + tc.context
        contextData = common.loadJson(contextSrc)
        sourceData = expand(sourceData, baseUri, null, ordered)
      }

      let expectedSrc = TESTSUITE_DIR + tc.expect
      let expectedData = common.loadJson(expectedSrc)
      if ('@context' in expectedData) {
        delete expectedData['@context']
      }

      let resultData
      if (contextData) {
        let compactArrays = options.compactArrays
        if (compactArrays === void(0)) compactArrays = true
        resultData = compact(contextData, sourceData, baseUri, compactArrays, ordered)
      } else {
        let expandContext = options.expandContext
        if (expandContext) {
            expandContext = TESTSUITE_DIR + expandContext
        }
        resultData = expand(sourceData, baseUri, expandContext, ordered)
      }

      t.deepEqual(resultData, expectedData)
      //t.equal(JSON.stringify(resultData, null, 2), JSON.stringify(expectedData, null, 2))
      t.end()
    })
  }
}

testCaseRunner('expand')
testCaseRunner('compact')
