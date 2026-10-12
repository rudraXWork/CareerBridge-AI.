const bullet = /^(?:[•●▪*]\s*|[-–]\s+|\d+[.)]\s+)/

export function groupProjects(lines) {
  const groups = []
  let current = null
  let wrapped = false
  let pending = false
  const text = lines.flatMap(line => line.split('\n')).map(line => line.trim()).filter(Boolean)
  for (let i = 0; i < text.length; i++) {
    const line = text[i]
    const marked = bullet.test(line) || pending
    pending = false
    const pipe = !marked ? line.indexOf('|') : -1
    const colon = !marked && !/^https?:/i.test(line) ? line.indexOf(':') : -1
    const plainTitle = !marked && !/[.!?]$/.test(line)
      && bullet.test(text[i + 1] || '') && !wrapped
    if (pipe > 0 || (colon > 0 && colon < 80) || plainTitle) {
      const split = pipe > 0 ? pipe : colon > 0 ? colon : line.length
      current = { title: line.slice(0, split).trim(), tools: '', bullets: [] }
      if (pipe > 0) current.tools = line.slice(split + 1).trim()
      else if (colon > 0) current.bullets.push(line.slice(split + 1).trim())
      groups.push(current)
      wrapped = false
      continue
    }
    if (!current) {
      current = { title: '', tools: '', bullets: [] }
      groups.push(current)
    }
    const body = line.replace(bullet, '').trim()
    if (!body) {
      pending = marked
      wrapped = false
      continue
    }
    if (!marked && wrapped) current.bullets[current.bullets.length - 1] += ' ' + body
    else current.bullets.push(body)
    wrapped = (marked || wrapped) && !/[.!?]$/.test(body)
  }
  return groups
}
