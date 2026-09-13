import { BrowserRouter, Route, Routes } from 'react-router-dom';

import Sidebar from './components/layout/Sidebar';
import BuildingPlanner from './pages/BuildingPlanner';
import CityPlanner from './pages/CityPlanner';
import WaterMicroplastics from './pages/WaterMicroplastics';

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-ink">
        <Sidebar />
        <Routes>
          <Route path="/" element={<CityPlanner />} />
          <Route path="/water" element={<WaterMicroplastics />} />
          <Route path="/building" element={<BuildingPlanner />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
