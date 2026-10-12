import { TZ } from '../booking/format'
import type { Qualification, Resource } from '../booking/types'

export type InductionStatus = 'NOT_SUBMITTED' | 'PENDING' | 'VERIFIED' | 'REJECTED' | 'EXPIRED'
export type Tone = 'grey' | 'amber' | 'green' | 'red'

export interface InductionView {
  status: InductionStatus
  tone: Tone
  label: string
  /** One sentence on where it stands. */
  detail: string
  /** What the student should do next, if anything. */
  action: 'upload' | 'reupload' | null
}

const dateFormat = new Intl.DateTimeFormat('en-AU', { dateStyle: 'medium', timeZone: TZ })
const dateOnly = (iso: string) => dateFormat.format(new Date(iso))

/** The backend decides eligibility from the latest submission for each requirement. */
export function latestByRequirement(qualifications: Qualification[]): Map<string, Qualification> {
  const latest = new Map<string, Qualification>()
  for (const item of qualifications) {
    const previous = latest.get(item.requirement_id)
    if (!previous || item.submitted_at >= previous.submitted_at) latest.set(item.requirement_id, item)
  }
  return latest
}

export function describeInduction(latest: Qualification | undefined): InductionView {
  const status: InductionStatus = latest?.effective_status ?? 'NOT_SUBMITTED'
  switch (status) {
    case 'VERIFIED':
      return { status, tone: 'green', label: 'Verified', action: null,
        detail: latest?.valid_until ? `Valid until ${dateOnly(latest.valid_until)}.` : 'You can book the resources it covers.' }
    case 'PENDING':
      return { status, tone: 'amber', label: 'Under review', action: null,
        detail: `Submitted ${latest ? dateOnly(latest.submitted_at) : ''}. Waiting for an admin to check it.` }
    case 'REJECTED':
      return { status, tone: 'red', label: 'Rejected', action: 'reupload',
        detail: latest?.rejection_reason ? `Reason: ${latest.rejection_reason}` : 'Please upload new evidence.' }
    case 'EXPIRED':
      return { status, tone: 'red', label: 'Expired', action: 'reupload',
        detail: latest?.valid_until ? `Expired on ${dateOnly(latest.valid_until)}. Upload it again to keep booking.` : 'Upload it again to keep booking.' }
    default:
      return { status, tone: 'grey', label: 'Not submitted', action: 'upload',
        detail: 'Upload your certificate to start booking.' }
  }
}

/** "Lab Room 1 and 10 devices" — what this induction lets the student book. */
export function unlocksText(requirementId: string, resources: Resource[]): string {
  const covered = resources.filter((r) => r.active && r.required_qualification_id === requirementId)
  if (!covered.length) return ''
  const rooms = covered.filter((r) => r.kind === 'ROOM').map((r) => r.name)
  const devices = covered.filter((r) => r.kind === 'EQUIPMENT').length
  const parts = [...rooms]
  if (devices) parts.push(`${devices} device${devices === 1 ? '' : 's'}`)
  return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}` : parts[0]
}
