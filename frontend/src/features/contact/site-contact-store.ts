// Sprint 3 (1.16.0): the lab's contact details, read once per page load (shared by every place that shows them).
import { useEffect, useState } from 'react'
import { getSiteContact } from '../booking/api'
import type { SiteContact } from '../booking/types'

let cached: Promise<SiteContact | null> | null = null

/** Forget the cached details (after a Manager saves new ones). */
export function refreshSiteContact() {
  cached = null
}

/** The lab's contact details, or null while loading or when they cannot be read. */
export function useSiteContact(): SiteContact | null {
  const [contact, setContact] = useState<SiteContact | null>(null)
  useEffect(() => {
    let alive = true
    cached ??= getSiteContact().catch(() => null)
    void cached.then((value) => { if (alive) setContact(value) })
    return () => { alive = false }
  }, [])
  return contact
}
