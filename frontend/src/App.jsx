import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar from './components/layout/Sidebar';
import Dashboard from './pages/Dashboard';
import WhatIfAnalysis from './pages/WhatIfAnalysis';
import CityCompare from './pages/CityCompare';

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-ink">
        <Sidebar />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/whatif" element={<WhatIfAnalysis />} />
          <Route path="/compare" element={<CityCompare />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
