import { HashRouter } from 'react-router'
import { AppRouter } from './app/AppRouter'
import { AuthProvider } from './features/auth/AuthProvider'
import { FeedbackProvider } from './ui/FeedbackProvider'
import './features/booking/booking.css'
import './app/shell.css'
import './ui/workspace.css' // Sprint 3: shared workspace visual system.

export default function App() {
  return (
    <FeedbackProvider>
      <HashRouter>
        <AuthProvider>
          <AppRouter />
        </AuthProvider>
      </HashRouter>
    </FeedbackProvider>
  )
}
