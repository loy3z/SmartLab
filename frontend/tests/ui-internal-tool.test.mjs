// Sprint 3 (internal-tool UI): acceptance checks for the plain "school internal tool" pass (claude/tasks-ui-internal-tool.md):
// one type scale, one font, two corner radii, no slogans or eyebrows, and one name per page. They read the source, so a
// later change that brings any of these back fails here instead of in a screenshot review.
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import test from 'node:test'
import { fmtClock, fmtHours } from '../src/features/booking/format.ts'

const src = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
const withoutComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, '')

// Every stylesheet the app imports (App.css is a leftover Vite file nothing imports).
const STYLESHEETS = ['ui/ui.css', 'ui/workspace.css', 'app/shell.css', 'index.css', 'features/booking/booking.css',
  'features/dashboard/dashboard.css', 'features/notifications/notifications.css', 'features/auth/auth.css', 'features/auth/mock-sso.css']
const TYPE_SCALE = new Set([12, 14, 16, 20, 24, 28])

function sourceFiles(dir = 'features', found = []) {
  for (const entry of readdirSync(new URL(`../src/${dir}`, import.meta.url), { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`
    if (entry.isDirectory()) sourceFiles(path, found)
    else if (/\.tsx?$/.test(entry.name)) found.push(path)
  }
  return found
}
const ALL_SOURCES = [...sourceFiles('features'), ...sourceFiles('app'), ...sourceFiles('ui')]

test('AI-3: every font size is on the type scale (12 / 14 / 16 / 20 / 24 / 28 px)', () => {
  for (const file of STYLESHEETS) {
    for (const [, value] of withoutComments(src(file)).matchAll(/font-size:\s*([^;}]+)/g)) {
      if (value.trim() === 'inherit') continue
      const px = /^(\d+(?:\.\d+)?)px$/.exec(value.trim())
      assert.ok(px, `${file}: font-size "${value.trim()}" is not a plain px value`)
      assert.ok(TYPE_SCALE.has(Number(px[1])), `${file}: font-size ${px[1]}px is not on the scale`)
    }
  }
})

test('AI-3: the H1 size is set in one shared rule (and its phone size); only the stand-in university sign-in page differs', () => {
  const h1Sizes = []
  for (const file of STYLESHEETS) {
    for (const [, selector, body] of withoutComments(src(file)).matchAll(/([^{}]*\bh1\b[^{}]*)\{([^}]*)\}/g)) {
      // Only selectors that style the H1 itself (not "h1 + p", the line under it).
      const stylesH1 = selector.split(/,(?![^(]*\))/).some((part) => /\bh1\)?$/.test(part.trim()) || /\bh1$/.test(part.trim()))
      if (stylesH1 && /font-size/.test(body)) h1Sizes.push(`${file}: ${selector.trim()}`)
    }
  }
  assert.deepEqual(h1Sizes, [
    'ui/workspace.css: :is(.app-content, .app-session-state, .auth-introduction) h1',
    'ui/workspace.css: :is(.app-content, .app-session-state, .auth-introduction) h1',
    'features/auth/mock-sso.css: .mock-sso-main h1',
  ])
})

test('AI-5: one font family (Manrope); the serif display font is gone', () => {
  for (const file of STYLESHEETS) {
    const css = withoutComments(src(file))
    assert.doesNotMatch(css, /Instrument Serif/, file)
    for (const [, family] of css.matchAll(/font-family:\s*([^;}]+)/g)) {
      if (file === 'features/auth/mock-sso.css') continue // stands in for the university's own (Microsoft) sign-in page
      assert.match(family.trim(), /^(Manrope\b|inherit$)/, `${file}: font-family ${family.trim()}`)
    }
  }
})

test('AI-5: corners are 8px (controls, badges) or 12px (cards, dialogs, tables); circles and pills stay round', () => {
  const allowed = new Set(['0', '8px', '12px', '50%', '999px', 'var(--radius-control)', 'var(--radius-panel)'])
  for (const file of STYLESHEETS) {
    const css = withoutComments(src(file))
    for (const [, value] of css.matchAll(/border-radius:\s*([^;}]+)/g)) {
      for (const token of value.trim().split(/\s+/)) assert.ok(allowed.has(token), `${file}: border-radius ${value.trim()}`)
    }
    for (const [, name, value] of css.matchAll(/--(radius-[a-z]+):\s*([^;]+)/g)) assert.ok(['8px', '12px'].includes(value.trim()), `${file}: --${name}`)
  }
})

test('AI-2: the slogans, eyebrows and introduction lines listed in the task are gone', () => {
  const removed = ['Welcome back', 'Your bookings, training and next steps', 'A time that works for you', 'Your time, then your space',
    'Set your time. Find a resource', 'Everything is in good order', 'A few things need your attention', 'Ready when you are',
    'starts here.', 'Your access to the lab', 'Shared space', 'YOUR PROFILE', 'A LITTLE GUIDANCE', 'Make the most of your',
    'Your identity and access', 'SPACES TO LEARN', 'next idea', 'SMARTLAB ACCESS', 'SMARTLAB STAFF', 'LOCAL DEVELOPMENT',
    'PAGE NOT FOUND', 'ACCESS RESTRICTED', '} Portal', 'Return to my portal', 'LAB &amp; RESOURCE BOOKING',
    'Choose a resource, or search for one', 'Your requests and their current status', 'those you made for other people',
    'Upload your training evidence. An admin checks it']
  for (const file of ALL_SOURCES) {
    const text = src(file)
    for (const phrase of removed) assert.ok(!text.includes(phrase), `${file} still contains "${phrase}"`)
  }
})

test('AI-2: no heading ends with a full stop', () => {
  for (const file of ALL_SOURCES) {
    for (const [heading] of src(file).matchAll(/<h[1-3][^>]*>[^<{]*\.<\/h[1-3]>/g)) assert.fail(`${file}: ${heading}`)
  }
})

test('AI-6: every menu item has the same sentence-case name as its browser-tab title', () => {
  const layout = src('app/AppLayout.tsx')
  const router = src('app/AppRouter.tsx')
  const titles = Object.fromEntries([...router.matchAll(/'(\/[a-z/-]+)': '([^']+)'/g)].map(([, path, title]) => [path, title]))
  const items = [...layout.matchAll(/path: '(\/[a-z/-]+)',\s*label: '([^']+)'/g)]
  assert.ok(items.length >= 13, 'menu items found')
  for (const [, path, label] of items) {
    assert.equal(label, titles[path], path)
    assert.equal(label, label[0] + label.slice(1).replace(/\b(?!I\b)[A-Z]/g, (letter) => letter.toLowerCase()), `${label} is sentence case`)
  }
})

test('AI-6: opening hours use the same "8:00 am" style as every other time', () => {
  assert.equal(fmtClock('08:00'), '8:00 am')
  assert.equal(fmtClock('20:00:00'), '8:00 pm')
  assert.equal(fmtClock('00:30:00'), '12:30 am')
  assert.equal(fmtHours('08:00:00', '20:00:00'), '8:00 am – 8:00 pm')
  // Pages show opening hours through fmtHours (resource-form.ts may still trim "08:00:00" for its time inputs).
  for (const file of ALL_SOURCES.filter((path) => path.endsWith('.tsx'))) assert.doesNotMatch(src(file), /_time\.slice\(0, 5\)/, file)
})
