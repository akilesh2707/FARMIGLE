import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/layout/Layout';
import FarmerHome from './pages/FarmerHome';
import PhotoAnalysis from './pages/PhotoAnalysis';
import OfficerDashboard from './pages/OfficerDashboard';
import ZoneDetail from './pages/ZoneDetail';
import MapPage from './pages/MapPage';
import AskPage from './pages/AskPage';
import ActionsPage from './pages/ActionsPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<FarmerHome />} />
          <Route path="/analyze" element={<PhotoAnalysis />} />
          <Route path="/officer" element={<OfficerDashboard />} />
          <Route path="/zones/:zoneId" element={<ZoneDetail />} />
          <Route path="/map" element={<MapPage />} />
          <Route path="/ask" element={<AskPage />} />
          <Route path="/actions" element={<ActionsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
