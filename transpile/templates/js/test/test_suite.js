import tape from 'tape'
import os from 'os'

import * as common from '../lib/common.js'
import * as context from '../lib/jsonld/context.js'
import { JSONLD10, CONTEXT, ID, TYPE } from '../lib/jsonld/base.js'
import { expand } from '../lib/jsonld/expansion.js'
import { compact } from '../lib/jsonld/compaction.js'
import { flatten } from '../lib/jsonld/flattening.js'

const TESTSUITE_DIR = `file://${process.env.TRLD_JSONLD_TESTDIR}/`
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
    if (tc[TYPE].indexOf('jld:PositiveEvaluationTest') === -1) {
      continue
    }
    let label = `${category} ${tc[ID]} - ${tc.purpose}`
    let options = tc.option || {}
    if (options.specVersion === JSONLD10) {
        continue
    }

    tape.test(label, t => {
      let src = TESTSUITE_DIR + tc.input
      let url = TESTSUITE_BASE_URL + tc.input
      let baseUri = options.base || url

      if (options.processingMode) {
        context.DEFAULT_PROCESSING_MODE = options.processingMode
      }

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
      if (CONTEXT in expectedData) {
        delete expectedData[CONTEXT]
      }

      let resultData

      let expandContext = null
      if (options.expandContext) {
          expandContext = TESTSUITE_DIR + options.expandContext
      }
      resultData = expand(sourceData, baseUri, expandContext, ordered)

      if (tc[TYPE].indexOf('jld:FlattenTest') > -1) {
          resultData = flatten(resultData, ordered)
      }

      if (contextData) {
        let compactArrays = options.compactArrays
        if (compactArrays === void(0)) compactArrays = true
        resultData = compact(contextData, sourceData, baseUri, compactArrays, ordered)
      }

      t.deepEqual(resultData, expectedData)
      //t.equal(JSON.stringify(resultData, null, 2), JSON.stringify(expectedData, null, 2))
      t.end()
    })
  }
}

testCaseRunner('expand')
testCaseRunner('compact')
testCaseRunner('flatten')
