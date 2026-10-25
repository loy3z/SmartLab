import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { changeTestSession } from '../booking/api'
import { errorMessage } from '../booking/format'
import type { Role, User } from '../booking/types'
import { getToken, setToken } from '../../lib/api-client'
import { canAccess, homePath } from '../../app/routes'

export function TestConsoleBar({ user }: { user: User }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const { pathname } = useLocation()
  async function change(role: Role, bypass: boolean) {
    if (busy) return
    const token = getToken()
    setBusy(true)
    setError('')
    try {
      const result = await changeTestSession(role, bypass)
      if (getToken() !== token) return
      if (!canAccess(pathname, role)) void navigate(homePath(role), { replace: true })
      setToken(result.access_token)
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }
  return <section className="test-console-bar" aria-label="Test console">
    <strong>Test account 1</strong>
    <label>View as
      <select aria-label="Test role" value={user.role} disabled={busy}
        onChange={e => void change(e.target.value as Role, Boolean(user.bypass_booking_rules))}>
        <option value="STUDENT">Student</option><option value="ADMIN">Admin</option><option value="MANAGER">Manager</option>
      </select>
    </label>
    <label><input type="checkbox" checked={Boolean(user.bypass_booking_rules)} disabled={busy}
      onChange={e => void change(user.role, e.target.checked)} /> Bypass booking rules</label>
    <span>{user.bypass_booking_rules ? 'ON · Free times are approved immediately. Conflict checks remain.' : 'OFF · Normal rules and approvals apply.'}</span>
    {error && <span role="alert">{error}</span>}
  </section>
}
