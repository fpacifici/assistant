import { Routes, Route, Navigate } from 'react-router';
import Layout from './components/Layout';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/notebooks" replace />} />
      <Route path="/notebooks" element={<Layout />} />
      <Route path="/notebooks/:notebookId/notes" element={<Layout />} />
      <Route path="/notebooks/:notebookId/notes/:noteId" element={<Layout />} />
    </Routes>
  );
}
