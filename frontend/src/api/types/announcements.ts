// Moved from the booking feature folder; definitions unchanged.

/** Attributed home-page announcement, separate from personal notifications. */
export interface Announcement {
  id: string; title: string; body: string; kind: 'MANUAL' | 'RESOURCE_STATUS'; resource_id: string | null
  created_by: string; author_role: 'ADMIN' | 'MANAGER'; author: { id: string; display_name: string; role: 'ADMIN' | 'MANAGER' }
  created_at: string; updated_at: string | null; expires_at: string | null; removed_at: string | null
  expected_back: string | null; active: boolean
}
