// Sprint 3: form rules for the Manager's resource setup page. The backend applies the same rules
// (backend/booking/services/resources.py, _check_resource_fields); these only give quicker messages.
import type { Resource, ResourceInput, ResourceKind } from '../../api/types/index.ts'

export const SLOT_CHOICES = [15, 30, 60] as const
export const MAX_DETAILS = 12 // Sprint 3 (1.16.0): "label: value" lines per resource (backend: resources.py MAX_DETAILS)

/** "08:00:00" or "08:00" -> minutes after midnight. */
export function toMinutes(value: string): number {
  const [hours, minutes] = value.split(':').map(Number)
  return hours * 60 + minutes
}

/** An empty form for a new room or equipment (same defaults as the backend). */
export function emptyResource(defaultRequirementId = ''): ResourceInput {
  return {
    name: '', location: '', description: '', required_qualification_id: defaultRequirementId, room_id: null, category: null,
    slot_minutes: 30, max_booking_minutes: 480, opening_time: '08:00', closing_time: '20:00', pending_hold_minutes: 1440,
    capacity: null, details: [], // Sprint 3 (1.16.0)
  }
}

/** The editable fields of an existing resource, with times as "HH:MM". */
export function resourceToInput(resource: Resource): ResourceInput {
  return {
    name: resource.name, location: resource.location, description: resource.description,
    required_qualification_id: resource.required_qualification_id ?? '', room_id: resource.room_id,
    category: resource.category ?? null, slot_minutes: resource.slot_minutes, max_booking_minutes: resource.max_booking_minutes,
    opening_time: resource.opening_time.slice(0, 5), closing_time: resource.closing_time.slice(0, 5),
    pending_hold_minutes: resource.pending_hold_minutes,
    capacity: resource.capacity ?? null, details: resource.details ?? [], // Sprint 3 (1.16.0)
  }
}

/** Problems to show next to the fields, keyed by field name. Empty when the form can be sent. */
export function checkResource(kind: ResourceKind, input: ResourceInput): Partial<Record<keyof ResourceInput, string>> {
  const problems: Partial<Record<keyof ResourceInput, string>> = {}
  if (!input.name.trim()) problems.name = 'Give a name.'
  if (!input.location.trim()) problems.location = 'Give a location.'
  if (!input.required_qualification_id) problems.required_qualification_id = 'Choose the induction people need.'
  if (kind === 'ROOM' && (input.room_id || input.category)) problems.room_id = 'A room is not kept in another room.'
  const slot = input.slot_minutes
  if (!SLOT_CHOICES.includes(slot as 15 | 30 | 60)) problems.slot_minutes = 'Use 15, 30 or 60 minutes.'
  const opening = toMinutes(input.opening_time)
  const closing = toMinutes(input.closing_time)
  if (!(closing > opening)) problems.closing_time = 'Closing time must be after opening time.'
  else if (opening % slot || closing % slot) problems.opening_time = `Use times on a ${slot}-minute step.`
  const longest = input.max_booking_minutes
  if (!Number.isInteger(longest) || longest < slot || longest % slot) {
    problems.max_booking_minutes = `Use whole steps of ${describeHours(slot)}.` // Sprint 3 (1.16.0): hours in the form
  } else if (closing > opening && longest > closing - opening) {
    problems.max_booking_minutes = 'It must fit within the opening hours.'
  }
  // Sprint 3 (1.16.0): capacity (rooms, 1-1000 people) and "label: value" details (same rules as the backend).
  if (input.capacity !== null) {
    if (kind !== 'ROOM') problems.capacity = 'Only rooms have a capacity.'
    else if (!Number.isInteger(input.capacity) || input.capacity < 1 || input.capacity > 1000) problems.capacity = 'Use a whole number of people from 1 to 1000.'
  }
  const filled = input.details.filter((item) => item.label.trim() || item.value.trim())
  if (filled.some((item) => !item.label.trim() || !item.value.trim() || item.label.trim().length > 40 || item.value.trim().length > 200)) {
    problems.details = 'Each detail needs a label (up to 40 characters) and a value (up to 200).'
  } else if (filled.length > MAX_DETAILS) {
    problems.details = `Add at most ${MAX_DETAILS} details.`
  }
  if (!Number.isInteger(input.pending_hold_minutes) || input.pending_hold_minutes < 1 || input.pending_hold_minutes > 20160) {
    problems.pending_hold_minutes = 'Use up to 336 hours (two weeks).' // Sprint 3 (1.16.0): hours in the form
  }
  return problems
}

/** Only the fields that changed, so an edit sends (and audits) just those. */
export function changedFields(before: ResourceInput, after: ResourceInput): Partial<ResourceInput> {
  const changes: Partial<ResourceInput> = {}
  for (const key of Object.keys(after) as (keyof ResourceInput)[]) {
    // Sprint 3 (1.16.0): details is a list, so compare its contents rather than the array object.
    const differs = key === 'details' ? JSON.stringify(before.details) !== JSON.stringify(after.details) : before[key] !== after[key]
    if (differs) (changes as Record<string, unknown>)[key] = after[key]
  }
  return changes
}

export const PROBLEM_TEXT: Record<string, string> = {
  OUTSIDE_OPENING_HOURS: 'outside the new opening hours',
  DURATION_LIMIT: 'longer than the new longest booking',
  INVALID_TIME_INCREMENT: 'not on the new time steps',
  QUALIFICATION_REQUIRED: 'the person lacks the new induction',
  RESOURCE_POLICY_NOT_CONFIGURED: 'no induction is set',
}

// Sprint 3 (1.16.0): the form shows lengths in hours (bookings are shown in hours everywhere else); the API keeps minutes.

/** Minutes -> hours for a number input (90 -> 1.5). */
export const hoursFromMinutes = (minutes: number) => minutes / 60

/** Hours typed in the form -> whole minutes for the API (1.5 -> 90). */
export const minutesFromHours = (hours: number) => Math.round(hours * 60)

/** Readable length: "1.5 h", "24 h (1 day)", "48 h (2 days)". */
export function describeHours(minutes: number): string {
  const hours = `${Number((minutes / 60).toFixed(2))} h`
  const days = minutes / 1440
  return minutes >= 1440 && Number.isInteger(days) ? `${hours} (${days} day${days === 1 ? '' : 's'})` : hours
}
