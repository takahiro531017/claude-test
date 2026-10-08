import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useCallback } from 'react'
import { AuthProvider, isAdmin, useAuth } from './auth/AuthContext'
import { useIdleLogout } from './hooks/useIdleLogout'
import { Login, MfaEnroll, MfaVerify, NoProfile, SetPassword } from './pages/AuthPages'
import Dashboard from './pages/Dashboard'
import RepairList from './pages/RepairList'
import RepairNew from './pages/RepairNew'
import RepairDetail from './pages/RepairDetail'
import Receipt from './pages/Receipt'
import Admin from './pages/Admin'
import { ROLE_LABEL } from './lib/types'

function Shell() {
  const { profile, masters, signOut } = useAuth()
  const out = useCallback(() => void signOut(), [signOut])
  useIdleLogout(masters.settings.session_timeout_min, out, true)
  const branch = masters.branches.find((b) => b.id === profile?.branch_id)?.name ?? '全拠点'
  return (
    <>
      <header className="topbar">
        <strong>修理品管理</strong>
        <nav>
          <NavLink to="/">ダッシュボード</NavLink>
          <NavLink to="/repairs">修理品一覧</NavLink>
          {(profile?.role === 'admin' || profile?.role === 'branch_staff') && <NavLink to="/repairs/new">新規受付</NavLink>}
          {isAdmin(profile) && <NavLink to="/admin">管理</NavLink>}
        </nav>
        <span className="who">{profile?.display_name}({ROLE_LABEL[profile!.role]}/{branch})
          <button className="btn small" onClick={out}>ログアウト</button></span>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/repairs" element={<RepairList />} />
          <Route path="/repairs/new" element={<RepairNew />} />
          <Route path="/repairs/:id" element={<RepairDetail />} />
          <Route path="/repairs/:id/receipt" element={<Receipt />} />
          <Route path="/admin" element={isAdmin(profile) ? <Admin /> : <Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  )
}

function Gate() {
  const { phase } = useAuth()
  switch (phase) {
    case 'loading': return <main className="auth-shell"><p>読み込み中…</p></main>
    case 'signedOut': return <Login />
    case 'setPassword': return <SetPassword />
    case 'mfaEnroll': return <MfaEnroll />
    case 'mfaVerify': return <MfaVerify />
    case 'noProfile': return <NoProfile />
    default: return <Shell />
  }
}
export default function App() { return <AuthProvider><Gate /></AuthProvider> }
