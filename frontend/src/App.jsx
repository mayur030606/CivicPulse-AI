import { Route, Routes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout.jsx'
import PublicOnlyRoute from './components/auth/PublicOnlyRoute.jsx'
import RequireAuth from './components/auth/RequireAuth.jsx'
import ComplaintsPage from './pages/ComplaintsPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import HomePage from './pages/HomePage.jsx'
import IncidentDetailPage from './pages/IncidentDetailPage.jsx'
import IncidentsPage from './pages/IncidentsPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import MapPage from './pages/MapPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'
import ReportPage from './pages/ReportPage.jsx'
import TrackingPage from './pages/TrackingPage.jsx'
import { STAFF_ROLES } from './lib/routeAccess.js'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="report" element={<ReportPage />} />
        <Route path="tracking" element={<TrackingPage />} />
        <Route path="complaints" element={<ComplaintsPage />} />
        <Route path="map" element={<MapPage />} />

        <Route
          path="login"
          element={
            <PublicOnlyRoute>
              <LoginPage />
            </PublicOnlyRoute>
          }
        />

        <Route element={<RequireAuth />}>
          <Route path="dashboard" element={<DashboardPage />} />
        </Route>

        <Route element={<RequireAuth roles={STAFF_ROLES} />}>
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="incidents/:incidentId" element={<IncidentDetailPage />} />
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
