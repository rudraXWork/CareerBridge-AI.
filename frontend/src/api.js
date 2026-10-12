export async function request(path, data, file) {
  const options = { method: data || file ? 'POST' : 'GET' }
  if (file) {
    const form = new FormData()
    form.append('file', file)
    options.body = form
  } else if (data) {
    options.headers = { 'Content-Type': 'application/json' }
    options.body = JSON.stringify(data)
  }
  let response
  try {
    response = await fetch(`/api${path}`, options)
  } catch {
    throw new Error('The backend is unavailable. Start it on port 8000, then try again.')
  }
  let result
  try {
    result = await response.json()
  } catch {
    throw new Error('The backend did not respond. Check that it is running on port 8000.')
  }
  if (!response.ok) {
    const detail = result.detail
    const message = Array.isArray(detail)
      ? detail.map(item => `${item.loc.slice(1).join(' · ')}: ${item.msg}`).join('. ')
      : detail || 'The request failed. Please try again.'
    throw new Error(message)
  }
  return result
}
