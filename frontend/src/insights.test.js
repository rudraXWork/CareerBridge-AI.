import assert from 'node:assert/strict'
import test from 'node:test'
import { rewriteProblem } from './insights.js'

test('existing copied insights are hidden, including cosmetic changes', () => {
  const original = 'Trained in drone technology, remote sensing and GIS.'
  assert.ok(rewriteProblem(original, original))
  assert.ok(rewriteProblem(original, '  trained in drone technology, remote sensing and GIS! '))
  assert.ok(rewriteProblem(original, ''))
})

test('existing insights cannot change ongoing work into a completed achievement', () => {
  assert.ok(rewriteProblem('Building a computer vision system for OBS.', 'Built a computer vision system for OBS.'))
  assert.ok(rewriteProblem('Architecting a Rust/Tauri desktop app.', 'Designed a Rust/Tauri desktop app.'))
})

test('a clearer rewrite retaining ongoing work is displayed', () => {
  assert.equal(rewriteProblem('Building a Python system that detects gestures and triggers OBS overlays.',
    'Developing a Python gesture-detection system to trigger overlays in OBS.'), '')
})

test('existing performance suggestions cannot discard a reported metric', () => {
  const original = 'Built and benchmarked six regression models; deployed the best Gradient Boosting model with an R2 score of 96.06% on Vercel and Render.'
  assert.ok(rewriteProblem(original, 'Built and benchmarked six regression models, selecting the Gradient Boosting model for deployment on Vercel and Render.'))
  assert.equal(rewriteProblem(original, 'Benchmarked six regression models and deployed the best, a Gradient Boosting model with an R2 score of 96.06%, on Vercel and Render.'), '')
})

test('a placeholder result is not offered as suggested wording', () => {
  assert.ok(rewriteProblem('Delivered a market intelligence application with real-time dashboards.',
    "Delivered a market intelligence application with real-time dashboards that reduced analysts' decision latency by X minutes."))
})
