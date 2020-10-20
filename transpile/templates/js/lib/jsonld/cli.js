'use(strict)'

import { loadJson, dumpJson } from './common.js'
import { expand } from './expansion.js'
import { compact } from './compaction.js'

export default async function main () {
  let docPath
  let contextPath

  let nextIsContext = false
  let args = process.argv.slice(2)
  for (let arg of args) {
    if (arg === '-c') {
      nextIsContext = true
      continue
    }
    if (nextIsContext) contextPath = arg
    else docPath = arg
    nextIsContext = false
  }

  let baseIri = docPath.indexOf('://') > -1 ? docPath : `file://${docPath}`

  let data = loadJson(docPath)
  let result = expand(data, baseIri)
  if (contextPath != null) {
    let context = loadJson(contextPath)
    result = compact(context, result, baseIri)
  }
  console.log(dumpJson(result, true))
}

if (typeof require !== 'undefined' && require.main === module) main()
