import assert from 'node:assert/strict'
import test from 'node:test'
import { groupProjects } from './projects.js'

test('separates pipe headings, tools and wrapped bullets without losing text', () => {
  const groups = groupProjects([
    'AIQuant | React, Node.js, Python GitHub ↗ LIVE ↗',
    '• Delivered a market intelligence application with',
    'real-time dashboards.',
    '• Built six regression models with an R2 score of 96.06%.',
    'Agent Control Plane | Python, FastAPI, SQLite',
    '• Developed a governance gateway for technical policy checks.',
    'MoneyTrail AI | React, D3.js, Flask',
    '• Analyzed transaction data to investigate financial crime.',
  ])
  assert.deepEqual(groups.map(p => p.title), ['AIQuant', 'Agent Control Plane', 'MoneyTrail AI'])
  assert.equal(groups[0].tools, 'React, Node.js, Python GitHub ↗ LIVE ↗')
  assert.deepEqual(groups[0].bullets, [
    'Delivered a market intelligence application with real-time dashboards.',
    'Built six regression models with an R2 score of 96.06%.',
  ])
})

test('keeps existing colon projects and recognizes a plain heading before bullets', () => {
  assert.deepEqual(groupProjects(['Sales dashboard: cleaned data using SQL.', 'Portfolio', '- Built a React website.']), [
    { title: 'Sales dashboard', tools: '', bullets: ['cleaned data using SQL.'] },
    { title: 'Portfolio', tools: '', bullets: ['Built a React website.'] },
  ])
})

test('does not invent a title for untitled statements or split a bullet at a colon', () => {
  assert.deepEqual(groupProjects(['• Improved response time: cached API results.', '• Added Python tests.']), [
    { title: '', tools: '', bullets: ['Improved response time: cached API results.', 'Added Python tests.'] },
  ])
  assert.deepEqual(groupProjects([]), [])
})

test('recognizes a long title directly before a bullet list', () => {
  const title = 'Unidentified & Wanted Surveillance Detection (UWSD) Real-Time AI Surveillance & Identity Recognition'
  assert.equal(groupProjects([title, '• Developed a surveillance pipeline using Python.'])[0].title, title)
})

test('joins a standalone PDF bullet glyph to its following statement', () => {
  assert.deepEqual(groupProjects(['•', 'Built a dashboard using SQL', 'to track sales.', '•'])[0].bullets,
    ['Built a dashboard using SQL to track sales.'])
})
