import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router'
import { Drawer, Facts } from '../../ui/components'
import { useFeedback } from '../../ui/feedback-context'
import { useAuth } from '../auth/auth-context'
import { listQualifications, listRequirements, listResources, submitQualification } from '../booking/api'
import { errorMessage, fmtDateTime } from '../booking/format'
import type { Qualification, Requirement, Resource } from '../booking/types'
import { EvidencePreview } from './EvidencePreview'
import { InductionRow } from './InductionRow'
import { blockingPrerequisite, describeInduction, latestByRequirement } from './status'
import { evidenceProblem } from './evidence'

export function InductionPage() {
  const feedback = useFeedback()
  const { user } = useAuth()
  const testAccount = Boolean(user?.test_account) // Sprint 3 (1.17.1): automatic grants need no evidence form.
  const [params, setParams] = useSearchParams()
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [qualifications, setQualifications] = useState<Qualification[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [requirementId, setRequirementId] = useState('')
  const [title, setTitle] = useState('')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [viewing, setViewing] = useState<Qualification | null>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const titleRef = useRef<HTMLInputElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const handledParam = useRef('')

  useEffect(() => {
    let active = true
    Promise.all([listRequirements(), listQualifications(), listResources({})])
      .then(([requirementsData, qualificationsData, resourceData]) => {
        if (!active) return
        setRequirements(requirementsData.results)
        setQualifications(qualificationsData.results)
        setResources(resourceData.results)
      })
      .catch((err: unknown) => active && setError(errorMessage(err)))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  const latest = latestByRequirement(qualifications)
  const blockedBy = (id: string) => {
    const requirement = requirements.find((item) => item.id === id)
    return requirement ? blockingPrerequisite(requirement, latest, requirements) : null
  }
  const canUpload = (id: string) => describeInduction(latest.get(id), blockedBy(id)).action !== null

  function startUpload(id: string) {
    setRequirementId(id)
    setUploadError('')
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    window.setTimeout(() => titleRef.current?.focus({ preventScroll: true }), 300)
  }

  // Deep link from the dashboard or a booking prompt: /induction?requirement=<id>
  const wanted = params.get('requirement') ?? ''
  useEffect(() => {
    if (loading || !wanted || handledParam.current === wanted) return
    handledParam.current = wanted
    const latestMap = latestByRequirement(qualifications)
    const current = latestMap.get(wanted)
    const target = requirements.find((r) => r.id === wanted)
    const view = describeInduction(current, target ? blockingPrerequisite(target, latestMap, requirements) : null)
    if (current && view.status === 'PENDING') {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setViewing(current)
    } else if (requirements.some((r) => r.id === wanted) && view.action !== null) {
      setRequirementId(wanted)
      formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      window.setTimeout(() => titleRef.current?.focus({ preventScroll: true }), 300)
    }
  }, [loading, wanted, qualifications, requirements])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    setUploadError('')

    const problem = !requirementId ? 'Select a training requirement.' : !title.trim() ? 'Enter a submission title.'
      : evidenceProblem(file) || (!canUpload(requirementId) ? 'This requirement is already verified or waiting for review.' : '')
    if (problem) {
      setUploadError(problem)
      return
    }

    const form = event.currentTarget
    setSubmitting(true)
    try {
      const submission = await submitQualification(requirementId, title.trim(), notes.trim(), file!)
      setQualifications((previous) => [submission, ...previous.filter((item) => item.id !== submission.id)])
      const name = requirements.find((r) => r.id === requirementId)?.name ?? 'Your induction'
      feedback.success(`${name} is now waiting for an admin to review it. You can book once it is verified.`, 'Evidence submitted')
      setRequirementId('')
      setTitle('')
      setNotes('')
      setFile(null)
      form.reset()
      if (params.has('requirement')) setParams({}, { replace: true })
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err: unknown) {
      const text = errorMessage(err)
      setUploadError(text)
      feedback.error(text, 'Upload failed')
    } finally {
      setSubmitting(false)
    }
  }

  const viewingRequirement = viewing ? requirements.find((r) => r.id === viewing.requirement_id) : undefined
  const fileProblem = evidenceProblem(file)
  const missing = !requirementId ? 'Select a training requirement.' : !title.trim() ? 'Enter a submission title.' : fileProblem

  return (
    <div>
      {/* Sprint 3 (internal-tool UI, AI-2 / AI-6): sentence-case name; the introduction line only for test account 1. */}
      <h1>Induction &amp; training</h1>
      {testAccount && <p className="bk-sub">All inductions are automatically verified for test account 1. No evidence upload is required.</p>}

      <section className="bk-bcard" style={{ alignItems: 'stretch' }}>
        <h2>My qualifications</h2>
        {loading && <p role="status">Loading qualifications…</p>}
        {error && <p className="bk-error" role="alert">{error}</p>}
        {!loading && !error && requirements.length === 0 && <p className="bk-muted">No training requirements are available yet.</p>}
        {!loading && !error && requirements.length > 0 && (
          <ul className="ind-list">
            {requirements.map((requirement) => (
              <li key={requirement.id}>
                <InductionRow
                  requirement={requirement}
                  latest={latest.get(requirement.id)}
                  resources={resources}
                  onUpload={startUpload}
                  onView={setViewing}
                  showDescription
                  blockedBy={blockedBy(requirement.id)}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      {!testAccount && <section className="bk-bcard" style={{ alignItems: 'stretch' }}>
        <h2>Submit induction evidence</h2>
        <p className="bk-muted">Upload a PDF, PNG or JPEG file, up to 5 MiB.</p>
        {uploadError && <p className="bk-error" role="alert">{uploadError}</p>}

        <form ref={formRef} onSubmit={handleSubmit} style={{ scrollMarginTop: 90 }}>
          <fieldset disabled={loading || !!error || submitting} style={{ border: 0, padding: 0, margin: 0, display: 'grid', gap: 16, maxWidth: 600, minWidth: 0 }}>
            <label className="ui-field">
              <span>Training requirement <span className="bk-required">Required</span></span>
              <select required value={requirementId} onChange={(event) => setRequirementId(event.target.value)}>
                <option value="">Select a training requirement</option>
                {requirements.map((requirement) => {
                  const lockedBy = blockedBy(requirement.id)
                  const view = describeInduction(latest.get(requirement.id), lockedBy)
                  return (
                    <option key={requirement.id} value={requirement.id} disabled={view.action === null}>
                      {requirement.name}{lockedBy && view.action === null ? ` (needs ${lockedBy} first)` : view.action === null ? ` (${view.label})` : ''}
                    </option>
                  )
                })}
              </select>
            </label>
            <label className="ui-field">
              <span>Submission title <span className="bk-required">Required</span></span>
              <input ref={titleRef} required maxLength={160} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. General laboratory induction certificate" />
            </label>
            <label className="ui-field">
              <span>Notes (optional)</span>
              <textarea rows={3} maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Anything the reviewer should know" />
            </label>
            <div className="ui-field">
              <label htmlFor="training-evidence">Training evidence <span className="bk-required">Required</span></label>
              <div className="ind-file-control">
                <input ref={fileRef} id="training-evidence" className="ind-file-input" type="file" required
                  accept=".pdf,.png,.jpg,.jpeg" aria-describedby="evidence-hint" aria-invalid={Boolean(file && fileProblem)}
                  onChange={(event) => { setFile(event.target.files?.[0] ?? null); setUploadError('') }} />
                <button type="button" className="ui-btn ui-btn-ghost" onClick={() => fileRef.current?.click()}>Choose file</button>
                <span className="ind-file-name">{file?.name ?? 'No file selected'}</span>
              </div>
              <small id="evidence-hint" className={file && fileProblem ? 'bk-error' : 'bk-muted'} role="status">
                {fileProblem || 'Training evidence selected. PDF, PNG or JPEG, up to 5 MiB.'}
              </small>
            </div>
            <button type="submit" className="bk-btn-yellow" style={{ justifySelf: 'start' }} disabled={Boolean(missing) || submitting}>
              {submitting ? 'Submitting…' : 'Submit for review'}
            </button>
            {missing && <p className="bk-missing" role="status">{missing}</p>}
          </fieldset>
        </form>
      </section>}

      {viewing && (
        <Drawer
          title={viewingRequirement?.name ?? 'Submission'}
          subtitle={describeInduction(viewing).label}
          onClose={() => {
            setViewing(null)
            if (params.has('requirement')) setParams({}, { replace: true })
          }}
        >
          <Facts items={[
            { label: 'Title', value: viewing.title },
            { label: 'Submitted', value: fmtDateTime(viewing.submitted_at) },
            { label: 'Status', value: describeInduction(viewing).detail },
            ...(viewing.notes ? [{ label: 'Notes', value: viewing.notes }] : []),
          ]} />
          <section>
            <h3>File</h3>
            <EvidencePreview submissionId={viewing.id} fileName={viewing.title} />
          </section>
        </Drawer>
      )}
    </div>
  )
}
