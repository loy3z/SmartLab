import { HashRouter } from 'react-router'
import { AppRouter } from './app/AppRouter'
import { AuthProvider } from './features/auth/AuthProvider'
import { FeedbackProvider } from './ui/FeedbackProvider'
import './features/booking/booking.css'
import './app/shell.css'

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
