import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchFarmHealth, fetchFarm, fetchFarms, runFarmAnalysis } from '../api/farms';
import type { HealthSummary, FarmDetail } from '../types';
import FarmDigitalTwin from '../components/domain/FarmDigitalTwin';
import { formatZoneName } from '../utils/zone';

export default function FarmerHome() {
  const [health, setHealth] = useState<HealthSummary | null>(null);
  const [farm, setFarm] = useState<FarmDetail | null>(null);
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
        
        await runFarmAnalysis(farmId); // Refresh analysis
        const [farmData, healthData] = await Promise.all([
          fetchFarm(farmId),
          fetchFarmHealth(farmId)
        ]);
        setFarm(farmData);
        setHealth(healthData);
      } catch (err) {
        console.error('Failed to load farm data', err);
        setErrorMsg('Failed to load farm data.');
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  if (loading) {
    return <div className="p-margin">Loading farm data...</div>;
  }

  if (errorMsg) {
    return <div className="p-margin text-error">{errorMsg}</div>;
  }

  if (!health || !farm) {
    return <div className="p-margin text-error">Failed to load farm data.</div>;
  }

  const getRiskZoneLabel = (zoneId: string) => {
    const zone = health.zones.find(z => z.zone_id === zoneId);
    return formatZoneName(zoneId, zone?.zone_label);
  };

  return (
    <div className="flex flex-col w-full px-margin pb-space-lg gap-space-md">
      {/* Greeting & Orchard Overview Header */}
      <section className="flex flex-col gap-space-xs mt-space-sm">
        <div className="flex items-center justify-between">
          <span className="font-technical-label text-technical-label text-on-surface-variant uppercase tracking-wider">
            Field Overview • காலை வணக்கம்
          </span>
          <span className="inline-flex items-center gap-1 font-technical-label text-technical-label text-secondary bg-[#E8F3ED] px-2 py-0.5 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-[#3F7658]"></span> Live Telemetry
          </span>
        </div>
        <h1 className="text-[28px] font-medium text-primary tracking-tight leading-tight">Welcome to Farmigle</h1>
        <p className="font-body-secondary text-body-secondary text-on-surface-variant capitalize">
          {farm.name} • {farm.area_hectares ? `${(farm.area_hectares * 2.47105).toFixed(1)} Acres` : 'Unknown Area'} • {farm.crop}
        </p>
        <div className="flex flex-wrap items-center gap-space-xs pt-1">
          <span className="font-technical-label text-technical-label text-primary-container bg-surface-container-highest px-2.5 py-1 rounded-[7px] font-medium tracking-wide uppercase">
            Stage: {health.crop_stage.replace('_', ' ')}
          </span>
          <span className="font-technical-label text-technical-label text-on-secondary-container bg-secondary-container px-2.5 py-1 rounded-[7px] font-medium tracking-wide flex items-center gap-1">
            <span className="material-symbols-outlined text-[14px]" style={{ fontVariationSettings: "'FILL' 1" }}>check_circle</span>
            Health: {health.status_counts['healthy'] || 0} Zones Healthy
          </span>
        </div>
      </section>

      {/* Ambient Field Intelligence Micro-Ticker */}
      {health.weather && (
        <section className="w-full bg-surface-container-low rounded-[10px] p-space-sm flex items-center justify-between text-on-surface-variant shadow-sm overflow-x-auto">
          <div className="flex items-center justify-between w-full text-body-secondary font-body-secondary px-1">
            <div className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[18px] text-primary">sunny</span>
              <span>{Math.round(health.weather.temperature_c || 30)}°C</span>
            </div>
            <span className="text-outline-variant">•</span>
            <div className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-[18px] text-primary">humidity_mid</span>
              <span>RH {Math.round(health.weather.humidity || 60)}%</span>
            </div>
            <span className="text-outline-variant">•</span>
            <div className="flex items-center gap-1.5 text-primary font-body-emphasis">
              <span className="material-symbols-outlined text-[18px]">satellite_alt</span>
              <span className="font-technical-label text-technical-label">Sentinel-2 Sync</span>
            </div>
          </div>
        </section>
      )}
      
      {/* Map Twin Component */}
      <FarmDigitalTwin zones={health.zones} />

      {/* 3 Summary Cards */}
      <section className="grid grid-cols-3 gap-2">
        <div className="bg-white p-3 rounded-[10px] shadow-sm flex flex-col justify-between border border-surface-variant">
          <span className="font-technical-label text-[10px] text-on-surface-variant uppercase tracking-wider">Farm Health</span>
          <div className="my-2 text-[28px] font-light text-primary leading-none tracking-tight">
            {health.status_counts['NO_DATA'] === health.zones_total ? 'Unknown' : 
             (health.status_counts['NEAR_READY'] || health.status_counts['READY'] || health.status_counts['healthy']) ? 'Good' : 'N/A'}
          </div>
          <div className="text-[10px] text-on-surface-variant">
            {health.status_counts['NO_DATA'] === health.zones_total ? 'Pending evidence' : 'Based on evidence'}
          </div>
        </div>
        <div className="bg-white p-3 rounded-[10px] shadow-sm flex flex-col justify-between border border-surface-variant">
          <span className="font-technical-label text-[10px] text-on-surface-variant uppercase tracking-wider">Top Priority</span>
          <div className="my-2 text-[22px] font-medium text-primary leading-none tracking-tight">
            {health.risks && health.risks.length > 0 ? getRiskZoneLabel(health.risks[0].zone_id) : 'None'}
          </div>
          <div className="text-[10px] font-medium text-primary line-clamp-1">
            {health.risks && health.risks.length > 0 ? health.risks[0].risk_level + ' Risk' : 'All clear'}
          </div>
        </div>
        <div className="bg-white p-3 rounded-[10px] shadow-sm flex flex-col justify-between border border-surface-variant">
          <span className="font-technical-label text-[10px] text-on-surface-variant uppercase tracking-wider">Window</span>
          <div className="my-2 text-[22px] font-light text-primary leading-none tracking-tight">
            {health.zones.find(z => z.estimated_harvest_window)?.estimated_harvest_window || 'N/A'}
          </div>
          <div className="text-[10px] text-on-surface-variant">
            {health.zones.find(z => z.estimated_harvest_window) ? 'Estimated' : 'Needs evidence'}
          </div>
        </div>
      </section>

      {/* Primary Action: View Harvest Map */}
      <Link to="/map" className="w-full h-11 bg-[#183C32] hover:bg-[#244F43] active:bg-[#122e26] text-white rounded-[7px] font-body-emphasis text-body-emphasis flex items-center justify-center gap-space-sm shadow-sm transition-colors">
        <span className="material-symbols-outlined text-[20px]">map</span>
        <span>View Harvest Map</span>
      </Link>

      {/* Secondary Quick Action Row */}
      <section className="grid grid-cols-2 gap-space-sm">
        <Link to="/analyze" className="w-full p-space-sm bg-white border border-surface-variant hover:bg-surface-container-lowest rounded-[10px] shadow-sm flex items-center gap-space-sm text-left transition-colors">
          <div className="w-10 h-10 rounded-[7px] bg-[#E8F3ED] flex items-center justify-center text-primary flex-shrink-0">
            <span className="material-symbols-outlined text-[22px]">photo_camera</span>
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-body-emphasis text-body-emphasis text-primary truncate leading-tight">Analyze Photo</span>
            <span className="font-technical-label text-technical-label text-on-surface-variant truncate">Instant crop check</span>
          </div>
        </Link>
        <Link to="/ask" className="w-full p-space-sm bg-white border border-surface-variant hover:bg-surface-container-lowest rounded-[10px] shadow-sm flex items-center gap-space-sm text-left transition-colors">
          <div className="w-10 h-10 rounded-[7px] bg-[#E8F3ED] flex items-center justify-center text-primary flex-shrink-0">
            <span className="material-symbols-outlined text-[22px]" style={{ fontVariationSettings: "'FILL' 1" }}>mic</span>
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-body-emphasis text-body-emphasis text-primary truncate leading-tight">Ask Farmigle</span>
            <span className="font-technical-label text-technical-label text-secondary font-medium truncate">தமிழில் கேளுங்கள்</span>
          </div>
        </Link>
      </section>

      {/* Subtle Field Observation Callout Card */}
      {health.risks && health.risks.length > 0 && (
        <div className="w-full bg-[#FAF5E6] rounded-[10px] p-space-md flex items-start gap-space-sm text-on-surface shadow-sm border border-[#EBE3CD]">
          <span className="material-symbols-outlined text-[#A95545] text-[20px] flex-shrink-0 mt-0.5">warning</span>
          <div className="flex flex-col gap-0.5">
            <span className="font-body-emphasis text-body-emphasis text-primary">
              {getRiskZoneLabel(health.risks[0].zone_id)}: Action required
            </span>
            <p className="font-body-secondary text-body-secondary text-on-surface-variant line-clamp-2">
              {health.risks[0].messages.join(' ')}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
