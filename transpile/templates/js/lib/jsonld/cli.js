'use(strict)'

import { loadJson, dumpJson } from './common.js'
import { expand } from './expansion.js'
import { compact } from './compaction.js'
import { flatten } from './flattening.js'

export default async function main () {
  let docPath
  let contextPath

  let nextIsContext = false
  let useFlatten = false
  let ordered = true
  let args = process.argv.slice(2)
  for (let arg of args) {
    if (arg === '-c') {
      nextIsContext = true
      continue
    }
    if (arg === '-f') {
      useFlatten = true
      continue
    }
    if (nextIsContext) contextPath = arg
    else docPath = arg
    nextIsContext = false
  }

  let baseIri = docPath.indexOf('://') > -1 ? docPath : `file://${docPath}`

  let data = loadJson(docPath)
  let expandContext = null
  let result = expand(data, baseIri, expandContext, ordered)
  if (useFlatten) {
      result = flatten(result, ordered)
  }
  if (contextPath != null) {
    let context = loadJson(contextPath)
    let compactArrays = true
    result = compact(context, result, baseIri, compactArrays, ordered)
  }
  console.log(dumpJson(result, true))
}

if (typeof require !== 'undefined' && require.main === module) main()
