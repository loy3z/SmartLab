import { Link } from 'react-router'
import type { User } from '../api/types/index.ts'
import { homePath } from './routes'
import { ChangePassword } from '../features/auth/ChangePassword' // Sprint 3
import { LabContactCard } from '../features/contact/LabContact' // Sprint 3 (1.16.0)
// Sprint 3 (1.19.0): settings now have a dedicated navigation entry.

export function AccountPage({ user }: { user: User }) {
  // Sprint 3 (internal-tool UI, AI-2): no eyebrow or introduction line above the details.
  return <section className="app-utility-page"><h1>Account details</h1><div className="app-card"><dl className="app-account-fields"><div><dt>Full name</dt><dd>{user.display_name}</dd></div><div><dt>University zID</dt><dd>{user.zid}</dd></div><div><dt>University email</dt><dd>{user.university_email || 'Not provided'}</dd></div><div><dt>Role</dt><dd>{user.role === 'STUDENT' ? 'Student' : user.role === 'ADMIN' ? 'Administrator' : 'Manager'}</dd></div><div><dt>Account status</dt><dd>{user.active ? 'Active' : 'Inactive'}</dd></div></dl><p className="app-page-description">To update your account details or access, contact your laboratory administrator.</p></div>{user.role !== 'STUDENT' && !user.test_account && <ChangePassword />}<div className="app-card"><Link to="/settings/notifications">Notification settings</Link></div></section>
}

export function HelpPage({ user }: { user: User }) {
  const student = user.role === 'STUDENT'
  // Sprint 3 (internal-tool UI, AI-2 / AI-6): no eyebrow or introduction line; page names as in the navigation.
  return <section className="app-utility-page"><h1>Help & support</h1><div className="app-help-grid">
    {student ? <>
      <article className="app-card"><h2>1. Check your induction</h2><p>Each resource has its own training requirement. Submit the relevant evidence and follow its review status.</p><Link to="/induction">Open induction & training →</Link></article>
      <article className="app-card"><h2>2. Find and book a resource</h2><p>Choose a room or piece of equipment, check its time slots, and submit your request. Only an Approved status confirms a booking.</p><Link to="/resources">Browse resources →</Link></article>
      <article className="app-card"><h2>3. Keep track of requests</h2><p>View approval and waitlist updates in My bookings. You can cancel future requests. To move an approved booking, use Change time: your booking stays until the new time is approved. Refresh the page to see the latest status.</p><Link to="/bookings">View my bookings →</Link></article>
    </> : <>
      <article className="app-card"><h2>Review induction evidence</h2><p>Review submitted documents, approve qualifications or explain why a student needs to resubmit. Induction review is separate from booking approval.</p><Link to="/admin/qualifications">Open induction review →</Link></article>
      <article className="app-card"><h2>Review booking requests</h2><p>Approve or reject requests before their review deadline; if nobody decides in time, the system approves requests that still follow the rules and rejects the rest. When a time frees up, the next waitlisted request moves to Awaiting approval.</p><Link to="/admin/bookings">Open booking review →</Link></article>
      <article className="app-card"><h2>Book for yourself or someone else</h2><p>Staff book under the same induction, opening-hours and conflict rules. Under Book for, choose Someone else and check their zID to book on their behalf; you are recorded as the creator and cannot approve that request yourself. Tick Urgent for a free time sooner than the normal booking window; a Manager must approve it.</p><Link to="/resources">Book a resource →</Link></article>
      {user.role === 'MANAGER' && <article className="app-card"><h2>Manage rooms and staff</h2><p>Put rooms under maintenance or reopen them, export bookings, and add staff accounts (give the new person their invite code; they activate it on the Staff sign-in page). Admins and Managers are separate staff roles fixed when the account is created. Only Managers reschedule bookings and decide urgent requests.</p><Link to="/manager/users">Open user management →</Link></article>}
    </>}
    {/* Sprint 3 (1.16.0): the lab's real contact details (set by a Manager on Lab setup). */}
    <article className="app-card"><LabContactCard title="Contact the lab" />{user.role === 'MANAGER' && <Link to="/manager/setup">Edit contact details →</Link>}</article>
    <article className="app-card"><h2>Calendar updates</h2><p>When Outlook integration is enabled, approved bookings can be sent to the connected calendar. A calendar sync failure does not cancel your booking. Contact your laboratory administrator if you need help.</p><Link to={homePath(user.role)}>Back to {user.role === 'STUDENT' ? 'Dashboard' : 'Today'} →</Link></article>
  </div></section>
}
