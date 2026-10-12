export function rewriteProblem(original, rewrite) {
  const normalize = text => text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim()
  if (!rewrite || normalize(original) === normalize(rewrite)) {
    return 'A useful rewrite needs more detail; your original wording is retained.'
  }
  const ongoing = 'building|architecting|developing|designing|implementing|creating|working on|planning|prototyping'
  if (new RegExp(`^(?:currently\\s+|actively\\s+|I am\\s+)?(?:${ongoing})\\b`, 'i').test(original)
    && !new RegExp(`\\b(?:${ongoing}|in progress|under development|ongoing)\\b`, 'i').test(rewrite)) {
    return 'The proposed wording changed the project’s ongoing status, so it was not used.'
  }
  const numbers = text => text.match(/\d+(?:[.,]\d+)*/g) || []
  const kept = new Set(numbers(rewrite))
  if (numbers(original).some(n => !kept.has(n))) {
    return 'The proposed wording removed numbers or metrics from your statement, so it was not used.'
  }
  if (/\b(?:X|Y|N)\s*(?:%|minutes\b|hours\b|days\b|users\b|records\b|percent\b)/i.test(rewrite)) {
    return 'The proposed wording needs a real result instead of a placeholder, so it was not used.'
  }
  return ''
}
