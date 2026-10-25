import { useEffect, useRef, type MouseEvent, type ReactNode } from 'react'

/** True when the pointer is on the dialog's backdrop (outside its box), not on its content. */
function onBackdrop(event: MouseEvent<HTMLDialogElement>) {
  if (event.target !== event.currentTarget) return false
  const bounds = event.currentTarget.getBoundingClientRect()
  return event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom
}

/**
 * Sprint 3 (workspace UI): a native modal dialog. Focus stays inside, Escape closes it, and focus returns to the
 * button that opened it.
 *
 * While it is open, everything outside it (toasts included) is inert and drawn under the backdrop, so content
 * shown in a Modal must also report errors inline; a toast alone cannot be read (review R1).
 * `label` is the dialog's accessible name, normally its visible heading (review R5).
 */
export function Modal({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  // Sprint 3 (review R4): close on a backdrop click only when the press also started there. Selecting text in a
  // field and releasing over the backdrop must not close the dialog and lose what was typed.
  const pressedOnBackdrop = useRef(false)
  useEffect(() => {
    const dialog = dialogRef.current
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog?.showModal()
    return () => {
      dialog?.close()
      document.body.style.overflow = previousOverflow
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus({ preventScroll: true })
    }
  }, [])
  return (
    <dialog
      ref={dialogRef}
      className="bk-native-dialog"
      aria-label={label}
      onCancel={(event) => { event.preventDefault(); onClose() }}
      onMouseDown={(event) => { pressedOnBackdrop.current = onBackdrop(event) }}
      onClick={(event) => {
        if (pressedOnBackdrop.current && onBackdrop(event)) onClose()
        pressedOnBackdrop.current = false
      }}
    >
      <div className="bk-modal">
        <button className="bk-close" aria-label="Close" onClick={onClose}>×</button>
        {children}
      </div>
    </dialog>
  )
}
