import { useEffect, useState } from 'react';
import { fetchFarms, fetchFarm, fetchFarmHealth } from '../api/farms';
import type { FarmDetail, HealthSummary } from '../types';
import FarmDigitalTwin from '../components/domain/FarmDigitalTwin';

export default function MapPage() {
  const [farm, setFarm] = useState<FarmDetail | null>(null);
  const [health, setHealth] = useState<HealthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const farmsList = await fetchFarms();
        if (!farmsList.farms || farmsList.farms.length === 0) {
           setErrorMsg('No farms available.');
           return;
        }
        const farmId = farmsList.farms[0].farm_id;
        const [farmData, healthData] = await Promise.all([
          fetchFarm(farmId),
          fetchFarmHealth(farmId)
        ]);
        setFarm(farmData);
        setHealth(healthData);
      } catch (err) {
        console.error('Failed to load map data', err);
        setErrorMsg('Failed to load map data.');
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  if (loading) return <div className="p-margin">Loading map...</div>;
  if (errorMsg) return <div className="p-margin text-error">{errorMsg}</div>;
  if (!farm || !health) return <div className="p-margin text-error">Failed to load farm data.</div>;

  return (
    <div className="flex flex-col w-full px-margin pb-space-lg gap-space-md">
      <div className="mt-space-sm flex flex-col gap-1">
        <h1 className="text-[28px] font-medium text-primary tracking-tight leading-tight">Farm Digital Twin</h1>
        <p className="text-[14px] text-on-surface-variant font-body-secondary">
          {farm.name} • {farm.area_hectares ? `${(farm.area_hectares * 2.47105).toFixed(1)} Acres` : 'Unknown Area'}
        </p>
      </div>
      
      {health.zones && health.zones.length > 0 ? (
        <div className="bg-[#E8F3ED] p-3 rounded-[12px] relative overflow-hidden mt-2 border border-[#d5e8de]">
          <div className="absolute top-3 left-3 flex items-center gap-1 font-technical-label text-[10px] tracking-wider text-secondary z-10">
            <span className="material-symbols-outlined text-[14px]">satellite_alt</span>
            LIVE TELEMETRY SYNC
          </div>
          <div className="mt-6">
            <FarmDigitalTwin zones={health.zones} />
          </div>
        </div>
      ) : (
        <div className="p-margin bg-surface-container rounded-[10px] text-center text-on-surface-variant font-body-default mt-2">
          No zones have been generated for this farm.
        </div>
      )}
    </div>
  );
}
