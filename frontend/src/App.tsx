import { Routes, Route, Navigate } from 'react-router';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import { AuthProvider } from './contexts/AuthContext';

function ProtectedRoutes() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Navigate to="/notebooks" replace />} />
        <Route path="/notebooks" element={<Layout />} />
        <Route path="/notebooks/:notebookId/notes" element={<Layout />} />
        <Route path="/notebooks/:notebookId/notes/:noteId" element={<Layout />} />
      </Routes>
    </AuthProvider>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/*" element={<ProtectedRoutes />} />
    </Routes>
  );
}
