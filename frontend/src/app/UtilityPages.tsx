import { Link } from 'react-router'
import type { User } from '../features/booking/types'
import { homePath } from './routes'

export function AccountPage({ user }: { user: User }) {
  return <section className="app-utility-page"><p className="app-eyebrow">YOUR PROFILE</p><h1>Account details</h1><p className="app-page-description">Your identity and access in SmartLab.</p><div className="app-card"><dl className="app-account-fields"><div><dt>Full name</dt><dd>{user.display_name}</dd></div><div><dt>University zID</dt><dd>{user.zid}</dd></div><div><dt>University email</dt><dd>{user.university_email || 'Not provided'}</dd></div><div><dt>Role</dt><dd>{user.role === 'STUDENT' ? 'Student' : user.role === 'ADMIN' ? 'Administrator' : 'Manager'}</dd></div><div><dt>Account status</dt><dd>{user.active ? 'Active' : 'Inactive'}</dd></div></dl><p className="app-page-description">To update your account details or access, contact your laboratory administrator.</p></div></section>
}

export function HelpPage({ user }: { user: User }) {
  const student = user.role === 'STUDENT'
  return <section className="app-utility-page"><p className="app-eyebrow">A LITTLE GUIDANCE</p><h1>Help & support</h1><p className="app-page-description">Make the most of your SmartLab portal.</p><div className="app-help-grid">
    {student ? <>
      <article className="app-card"><h2>1. Check your induction</h2><p>Each resource has its own training requirement. Submit the relevant evidence and follow its review status.</p><Link to="/induction">Open induction & training →</Link></article>
      <article className="app-card"><h2>2. Find and book a resource</h2><p>Choose a room or piece of equipment, check its time slots, and submit your request. Only an Approved status confirms a booking.</p><Link to="/resources">Browse resources →</Link></article>
      <article className="app-card"><h2>3. Keep track of requests</h2><p>View approval and waitlist updates in My Bookings. You can cancel future requests or reschedule eligible approved bookings. Refresh the page to see the latest status.</p><Link to="/bookings">View my bookings →</Link></article>
    </> : <>
      <article className="app-card"><h2>Review induction evidence</h2><p>Review submitted documents, approve qualifications or explain why a student needs to resubmit. Qualification review is separate from booking approval.</p><Link to="/admin/qualifications">Open qualification review →</Link></article>
      <article className="app-card"><h2>Review booking requests</h2><p>Approve or reject requests before their review deadline; if nobody decides in time, the system approves requests that still follow the rules and rejects the rest. When a time frees up, the next waitlisted request moves to Awaiting approval.</p><Link to="/admin/bookings">Open booking review →</Link></article>
    </>}
    <article className="app-card"><h2>Calendar updates</h2><p>When Outlook integration is enabled, approved bookings can be sent to the connected calendar. A calendar sync failure does not cancel your booking. Contact your laboratory administrator if you need help.</p><Link to={homePath(user.role)}>Return to my portal →</Link></article>
  </div></section>
}
