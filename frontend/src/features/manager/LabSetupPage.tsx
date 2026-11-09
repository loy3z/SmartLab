// Sprint 3 (1.16.0): Lab setup (Manager) — induction types and their guidance, and the lab's contact details.
// The client fills these in themselves; nothing here is fixed in code. Rules live in the backend
// (services/qualifications.py create/update_requirement, services/site_contact.py).
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { DialogTitle, PageHeader, Tabs } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { createRequirement, getSiteContact, listRequirements, updateRequirement, updateSiteContact } from '../../api/index.ts'
import { errorMessage } from '../booking/format'
import type { Requirement, RequirementInput, SiteContact } from '../../api/types/index.ts'
import { refreshSiteContact } from '../contact/site-contact-store'
import { GUIDE_LABELS, guideItems } from '../induction/guide'
import { emptyRequirement, requirementChanges, requirementToInput } from './lab-setup'

type Tab = 'inductions' | 'contact'

export function LabSetupPage() {
  const [tab, setTab] = useState<Tab>('inductions')
  return (
    <section>
      <PageHeader title="Lab setup" />
      <Tabs value={tab} onChange={setTab} label="Lab setup" items={[{ key: 'inductions', label: 'Inductions' }, { key: 'contact', label: 'Contact details' }]} />
      {tab === 'inductions' ? <InductionsTab /> : <ContactTab />}
    </section>
  )
}

function InductionsTab() {
  const [items, setItems] = useState<Requirement[]>([])
  const [editing, setEditing] = useState<Requirement | 'new' | null>(null)
  const [error, setError] = useState('')
  const reload = useCallback(() => {
    listRequirements().then((r) => (setItems(r.results), setError(''))).catch((e) => setError(errorMessage(e)))
  }, [])
  useEffect(() => { reload() }, [reload])
  const name = (id: string) => items.find((item) => item.id === id)?.name ?? 'Unknown'

  return (
    <>
      <div className="mr-toolbar"><button type="button" className="ui-btn ui-btn-primary" onClick={() => setEditing('new')}>+ Add induction</button></div>
      {error && <p className="bk-error" role="alert">{error}</p>}
      <div className="ui-table-wrap">
        <table className="ui-table">
          <thead><tr><th>Induction</th><th>Needs first</th><th>Guidance for newcomers</th><th><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {items.map((item) => {
              const written = guideItems(item).length
              return (
                <tr key={item.id}>
                  <td><span className="ui-primary-text">{item.name}</span>{item.description && <span className="ui-sub-text">{item.description}</span>}</td>
                  <td>{item.prerequisite_ids.length ? item.prerequisite_ids.map(name).join(', ') : '—'}</td>
                  <td>{written ? `${written} of 4 written` : <span className="ui-pill is-amber">Not written yet</span>}</td>
                  <td><button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={() => setEditing(item)}>Edit</button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {editing && <InductionDialog requirement={editing === 'new' ? null : editing} all={items}
        onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />}
    </>
  )
}

function InductionDialog({ requirement, all, onClose, onSaved }: {
  requirement: Requirement | null
  all: Requirement[]
  onClose: () => void
  onSaved: () => void
}) {
  const feedback = useFeedback()
  const ref = useRef<HTMLDialogElement>(null)
  const [initial] = useState<RequirementInput>(() => (requirement ? requirementToInput(requirement) : emptyRequirement()))
  const [form, setForm] = useState<RequirementInput>(initial)
  const [prerequisites, setPrerequisites] = useState<string[]>(requirement?.prerequisite_ids ?? [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { const dialog = ref.current; if (dialog && !dialog.open) dialog.showModal() }, [])
  const set = (key: keyof RequirementInput, value: string) => setForm((current) => ({ ...current, [key]: value }))
  const others = all.filter((item) => item.id !== requirement?.id)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy || !form.name.trim()) return
    setBusy(true)
    setError('')
    try {
      const prereqChanged = JSON.stringify([...prerequisites].sort()) !== JSON.stringify([...(requirement?.prerequisite_ids ?? [])].sort())
      if (requirement) {
        const changes = requirementChanges(initial, form)
        if (Object.keys(changes).length || prereqChanged) {
          await updateRequirement(requirement.id, { ...changes, ...(prereqChanged ? { prerequisite_ids: prerequisites } : {}) })
        }
      } else {
        const created = await createRequirement(form)
        if (prerequisites.length) await updateRequirement(created.id, { prerequisite_ids: prerequisites })
      }
      feedback.success(form.name.trim(), requirement ? 'Induction saved' : 'Induction added')
      onSaved()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <dialog ref={ref} className="ui-dialog ui-dialog-form" aria-labelledby="induction-dialog-title" onCancel={(e) => { e.preventDefault(); onClose() }}>
      <form className="ui-dialog-card" onSubmit={submit}>
        <DialogTitle id="induction-dialog-title" title={requirement ? `Edit ${requirement.name}` : 'Add induction'} onClose={onClose} />
        {requirement && <p className="ui-dialog-message">People who already hold this induction keep it.</p>}
        <label className="ui-field"><span>Name</span><input required maxLength={120} value={form.name} onChange={(e) => set('name', e.target.value)} /></label>
        <label className="ui-field"><span>Description (optional)</span>
          <textarea maxLength={1000} rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} />
        </label>
        <fieldset className="mr-details mr-two-columns">
          <legend>For people who do not have it yet (shown on Induction &amp; training)</legend>
          {(Object.keys(GUIDE_LABELS) as (keyof typeof GUIDE_LABELS)[]).map((key) => (
            <label key={key} className="ui-field"><span>{GUIDE_LABELS[key]}</span>
              <textarea maxLength={2000} rows={2} value={form[key]} placeholder={GUIDE_PLACEHOLDERS[key]} onChange={(e) => set(key, e.target.value)} />
            </label>
          ))}
        </fieldset>
        {others.length > 0 && (
          <fieldset className="mr-details">
            <legend>Must be verified first (optional)</legend>
            {others.map((item) => (
              <label key={item.id} className="mr-check">
                <input type="checkbox" checked={prerequisites.includes(item.id)}
                  onChange={(e) => setPrerequisites((list) => (e.target.checked ? [...list, item.id] : list.filter((id) => id !== item.id)))} />
                {item.name}
              </label>
            ))}
          </fieldset>
        )}
        {error && <p className="bk-error" role="alert">{error}</p>}
        <div className="ui-dialog-actions">
          <button type="button" className="ui-btn ui-btn-ghost" onClick={onClose}>Cancel</button>
          <button type="submit" className="ui-btn ui-btn-primary" disabled={busy || !form.name.trim()}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </dialog>
  )
}

const GUIDE_PLACEHOLDERS: Record<keyof typeof GUIDE_LABELS, string> = {
  how_to_complete: 'e.g. Book a session with the lab technician, or complete the online module',
  accepted_evidence: 'e.g. A PDF of the completion certificate',
  reviewer: 'e.g. The lab administrator checks it within two working days',
  contact: 'e.g. Name and email of the person to ask',
}

function ContactTab() {
  const feedback = useFeedback()
  const [form, setForm] = useState<SiteContact | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { getSiteContact().then(setForm).catch((e) => setError(errorMessage(e))) }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!form || busy) return
    setBusy(true)
    setError('')
    try {
      setForm(await updateSiteContact({ email: form.email, phone: form.phone, hours: form.hours, note: form.note }))
      refreshSiteContact()
      feedback.success('Shown on Help & support, My bookings and Induction & training.', 'Contact details saved')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  if (!form) return error ? <p className="bk-error" role="alert">{error}</p> : <p role="status">Loading…</p>
  const set = (key: keyof SiteContact, value: string) => setForm({ ...form, [key]: value })
  return (
    <form className="bk-bcard mr-contact" onSubmit={submit}>
      <p className="bk-muted">People see these on the Help page, on their approved bookings (an email with the booking already named) and under each induction. Leave a field empty to hide it.</p>
      <label className="ui-field"><span>Email</span><input type="email" maxLength={200} value={form.email} onChange={(e) => set('email', e.target.value)} /></label>
      <label className="ui-field"><span>Phone</span><input maxLength={60} value={form.phone} onChange={(e) => set('phone', e.target.value)} /></label>
      <label className="ui-field"><span>When someone answers</span><input maxLength={200} value={form.hours} placeholder="e.g. Mon–Fri 9 am–5 pm" onChange={(e) => set('hours', e.target.value)} /></label>
      <label className="ui-field"><span>Note</span><textarea maxLength={1000} rows={3} value={form.note} placeholder="e.g. Where to find the lab office" onChange={(e) => set('note', e.target.value)} /></label>
      {error && <p className="bk-error" role="alert">{error}</p>}
      <div><button type="submit" className="ui-btn ui-btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save contact details'}</button></div>
    </form>
  )
}
