// Sprint 3 (1.16.0): the lab's contact details shown on Help, My Bookings and Induction & Training.
import { useSiteContact } from './site-contact-store'
import { hasContact, mailtoLink } from './contact'

/** Full card (Help page, induction guidance). Says so when the lab has not added details yet. */
export function LabContactCard({ title = 'Contact the lab', subject = 'SmartLab question' }: { title?: string; subject?: string }) {
  const contact = useSiteContact()
  return (
    <div className="lab-contact">
      <h3>{title}</h3>
      {!hasContact(contact) ? (
        <p className="bk-muted">The lab has not added contact details yet.</p>
      ) : (
        <dl>
          {contact!.email && <div><dt>Email</dt><dd><a href={mailtoLink(contact, subject)}>{contact!.email}</a></dd></div>}
          {contact!.phone && <div><dt>Phone</dt><dd><a href={`tel:${contact!.phone.replace(/[^\d+]/g, '')}`}>{contact!.phone}</a></dd></div>}
          {contact!.hours && <div><dt>When</dt><dd>{contact!.hours}</dd></div>}
          {contact!.note && <div><dt>Note</dt><dd>{contact!.note}</dd></div>}
        </dl>
      )}
    </div>
  )
}

/** One line with a prefilled email (e.g. on a booking card). Nothing when there is no email. */
export function ContactLink({ label, subject, body }: { label: string; subject: string; body?: string }) {
  const contact = useSiteContact()
  const href = mailtoLink(contact, subject, body)
  return href ? <a className="lab-contact-link" href={href}>{label}</a> : null
}
