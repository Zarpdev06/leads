import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Layout from './components/layout/Layout'
import { Toaster, Spinner } from './components/ui'
import { useAuth } from './context/AuthContext'

import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Leads from './pages/Leads'
import LeadDetail from './pages/LeadDetail'
import MissingEmail from './pages/MissingEmail'
import Companies from './pages/Companies'
import Contacts from './pages/Contacts'
import Imports from './pages/Imports'
import ImportDetail from './pages/ImportDetail'
import Campaigns from './pages/Campaigns'
import CampaignNew from './pages/CampaignNew'
import CampaignDetail from './pages/CampaignDetail'
import Email from './pages/Email'
import FollowUps from './pages/FollowUps'
import CRM from './pages/CRM'
import Analytics from './pages/Analytics'
import Suppression from './pages/Suppression'
import AI from './pages/AI'
import Settings from './pages/Settings'
import AuditLogs from './pages/AuditLogs'
import Unsubscribe from './pages/Unsubscribe'

function Protected({ children, manager, admin }) {
  const { user, loading, isManager, isAdmin } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner className="h-6 w-6" />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  if (manager && !isManager) return <Navigate to="/dashboard" replace />
  if (admin && !isAdmin) return <Navigate to="/dashboard" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  const { isAuthenticated } = useAuth()

  return (
    <>
      <Routes>
        <Route path="/login" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Login />} />
        <Route path="/unsubscribe/:token" element={<Unsubscribe />} />

        <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
        <Route path="/leads" element={<Protected><Leads /></Protected>} />
        <Route path="/leads/missing-email" element={<Protected><MissingEmail /></Protected>} />
        <Route path="/leads/:id" element={<Protected><LeadDetail /></Protected>} />
        <Route path="/companies" element={<Protected><Companies /></Protected>} />
        <Route path="/contacts" element={<Protected><Contacts /></Protected>} />
        <Route path="/imports" element={<Protected><Imports /></Protected>} />
        <Route path="/imports/:id" element={<Protected><ImportDetail /></Protected>} />
        <Route path="/campaigns" element={<Protected><Campaigns /></Protected>} />
        <Route path="/campaigns/new" element={<Protected><CampaignNew /></Protected>} />
        <Route path="/campaigns/:id" element={<Protected><CampaignDetail /></Protected>} />
        <Route path="/follow-ups" element={<Protected><FollowUps /></Protected>} />
        <Route path="/email" element={<Protected manager><Email /></Protected>} />
        <Route path="/crm" element={<Protected><CRM /></Protected>} />
        <Route path="/analytics" element={<Protected><Analytics /></Protected>} />
        <Route path="/suppression" element={<Protected><Suppression /></Protected>} />
        <Route path="/ai" element={<Protected manager><AI /></Protected>} />
        <Route path="/settings" element={<Protected manager><Settings /></Protected>} />
        <Route path="/audit-logs" element={<Protected admin><AuditLogs /></Protected>} />

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
      <Toaster />
    </>
  )
}
