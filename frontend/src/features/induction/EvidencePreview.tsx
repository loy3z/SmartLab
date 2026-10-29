import { useEffect, useState } from 'react'
import { downloadQualification } from '../../api/index.ts'
import { errorMessage } from '../booking/format'

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; url: string; type: string; blob: Blob }

function extension(type: string) {
  return type === 'application/pdf' ? '.pdf' : type === 'image/png' ? '.png' : type === 'image/jpeg' ? '.jpg' : ''
}

/** Shows an uploaded induction file inline (PDF or image); the file is fetched with the signed-in token. */
export function EvidencePreview({ submissionId, fileName }: { submissionId: string; fileName?: string }) {
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let active = true
    let url = ''
    downloadQualification(submissionId)
      .then((blob) => {
        if (!active) return
        url = URL.createObjectURL(blob)
        setState({ status: 'ready', url, type: blob.type, blob })
      })
      .catch((e) => active && setState({ status: 'error', message: errorMessage(e) }))
    return () => {
      active = false
      if (url) URL.revokeObjectURL(url)
    }
  }, [submissionId])

  if (state.status === 'loading') return <p className="bk-muted" role="status">Loading the file…</p>
  if (state.status === 'error') return <p className="bk-error" role="alert">Could not load the file: {state.message}</p>

  const name = `${fileName || `evidence-${submissionId}`}${extension(state.type)}`
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      {state.type === 'application/pdf'
        ? <iframe className="ui-preview" src={state.url} title="Evidence preview" />
        : state.type.startsWith('image/')
          ? <img className="ui-preview-img" src={state.url} alt="Uploaded evidence" />
          : <p className="bk-muted">This file type cannot be previewed.</p>}
      <a className="ui-btn ui-btn-ghost ui-btn-sm" style={{ justifySelf: 'start' }} href={state.url} download={name}>Download file</a>
    </div>
  )
}
