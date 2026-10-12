import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { FeedbackContext, type ConfirmOptions, type ConfirmResult, type Feedback, type ToastTone } from './feedback-context'
import './ui.css'

interface Toast {
  id: number
  tone: ToastTone
  title?: string
  message: string
}

interface PendingConfirm extends ConfirmOptions {
  resolve: (result: ConfirmResult) => void
}

const SUCCESS_MS = 4500
let nextId = 1

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [pending, setPending] = useState<PendingConfirm | null>(null)
  const timers = useRef(new Map<number, number>())

  const dismiss = useCallback((id: number) => {
    setToasts((list) => list.filter((item) => item.id !== id))
    const timer = timers.current.get(id)
    if (timer) window.clearTimeout(timer)
    timers.current.delete(id)
  }, [])

  const push = useCallback((tone: ToastTone, message: string, title?: string) => {
    const id = nextId++
    // Keep the stack short; errors stay until dismissed so the reason can be read.
    setToasts((list) => [...list.slice(-3), { id, tone, title, message }])
    if (tone !== 'error') timers.current.set(id, window.setTimeout(() => dismiss(id), SUCCESS_MS))
  }, [dismiss])

  useEffect(() => {
    const all = timers.current
    return () => all.forEach((timer) => window.clearTimeout(timer))
  }, [])

  const confirm = useCallback((options: ConfirmOptions) => new Promise<ConfirmResult>((resolve) => {
    setPending((previous) => {
      previous?.resolve({ confirmed: false, reason: '' })
      return { ...options, resolve }
    })
  }), [])

  const value = useMemo<Feedback>(() => ({
    success: (message, title) => push('success', message, title),
    error: (message, title) => push('error', message, title),
    info: (message, title) => push('info', message, title),
    confirm,
  }), [push, confirm])

  return (
    <FeedbackContext.Provider value={value}>
      {children}
      <div className="ui-toasts" aria-live="polite" aria-relevant="additions">
        {toasts.map((toast) => (
          <div key={toast.id} className={`ui-toast is-${toast.tone}`} role={toast.tone === 'error' ? 'alert' : 'status'}>
            <span className="ui-toast-icon" aria-hidden="true">{toast.tone === 'success' ? '✓' : toast.tone === 'error' ? '!' : 'i'}</span>
            <div className="ui-toast-body">
              <strong>{toast.title ?? (toast.tone === 'success' ? 'Done' : toast.tone === 'error' ? 'Something went wrong' : 'Note')}</strong>
              <p>{toast.message}</p>
            </div>
            <button type="button" className="ui-toast-close" aria-label="Dismiss notification" onClick={() => dismiss(toast.id)}>×</button>
          </div>
        ))}
      </div>
      {pending && (
        <ConfirmDialog
          key={pending.title + (pending.message ?? '')}
          options={pending}
          onClose={(result) => {
            pending.resolve(result)
            setPending(null)
          }}
        />
      )}
    </FeedbackContext.Provider>
  )
}

function ConfirmDialog({ options, onClose }: { options: ConfirmOptions; onClose: (result: ConfirmResult) => void }) {
  const [reason, setReason] = useState('')
  const dialogRef = useRef<HTMLDialogElement>(null)
  const reasonRequired = Boolean(options.reason && options.reason.required !== false)
  const blocked = reasonRequired && !reason.trim()

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  const cancel = () => onClose({ confirmed: false, reason: '' })

  return (
    <dialog
      ref={dialogRef}
      className="ui-dialog"
      aria-labelledby="ui-dialog-title"
      onCancel={(event) => { event.preventDefault(); cancel() }}
      onClick={(event) => { if (event.target === event.currentTarget) cancel() }}
    >
      <form
        method="dialog"
        className="ui-dialog-card"
        onSubmit={(event) => {
          event.preventDefault()
          if (!blocked) onClose({ confirmed: true, reason: reason.trim() })
        }}
      >
        <h2 id="ui-dialog-title">{options.title}</h2>
        {options.message && <p className="ui-dialog-message">{options.message}</p>}
        {options.details && options.details.length > 0 && (
          <dl className="ui-dialog-details">
            {options.details.map((item) => (
              <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>
            ))}
          </dl>
        )}
        {options.reason && (
          <label className="ui-field">
            <span>{options.reason.label}{reasonRequired ? '' : ' (optional)'}</span>
            <textarea
              autoFocus
              rows={3}
              maxLength={options.reason.maxLength ?? 2000}
              placeholder={options.reason.placeholder}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
        )}
        <div className="ui-dialog-actions">
          <button type="button" className="ui-btn ui-btn-ghost" onClick={cancel}>{options.cancelLabel ?? 'Cancel'}</button>
          <button type="submit" className={`ui-btn ${options.danger ? 'ui-btn-danger' : 'ui-btn-primary'}`} disabled={blocked} autoFocus={!options.reason}>
            {options.confirmLabel ?? 'Confirm'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
