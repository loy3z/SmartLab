// Sprint 3 (1.15.0): which picture a resource card shows until real photos are added.
import type { Resource } from '../../api/types/index.ts'

/** Cover groups. Each has its own colour and line icon (see ResourceCover in ResourceCard.tsx and booking.css). */
export type CoverKey = 'room' | 'microscopy' | 'imaging' | 'electronics' | 'soldering' | 'fabrication' | 'analysis' | 'equipment'

// Checked in order; the first match wins. Matching words rather than exact category names means
// categories a Manager types later (e.g. "Microscopes", "3D printing") still get a sensible cover.
const RULES: [CoverKey, RegExp][] = [
  ['microscopy', /microscop/i],
  ['imaging', /imag|camera|thermal|photo/i],
  ['soldering', /solder|fume/i],
  ['fabrication', /fabricat|3d print|printer|laser|cutter|cnc/i],
  ['electronics', /electr|oscillo|multimeter|signal|power supply|logic|data logger/i],
  ['analysis', /analy|spectro|centrifug|chemi|bio/i],
]

/**
 * Cover for a resource card.
 * Rooms always get "room". Equipment is matched on its category first, then its name; no match → "equipment".
 */
export function coverKey(resource: Pick<Resource, 'kind' | 'name' | 'category'>): CoverKey {
  if (resource.kind === 'ROOM') return 'room'
  for (const text of [resource.category ?? '', resource.name]) {
    const rule = RULES.find(([, pattern]) => pattern.test(text))
    if (rule) return rule[0]
  }
  return 'equipment'
}
