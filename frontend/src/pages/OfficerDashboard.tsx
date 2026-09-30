import { useEffect, useState } from 'react';
import { api } from '../api/client';

export default function OfficerDashboard() {
  const [hotspots, setHotspots] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const districtId = 'district_theni_01'; // hardcoded demo district

  useEffect(() => {
    api.get(`/districts/${districtId}/hotspots`)
      .then(res => setHotspots(res))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex flex-col w-full px-margin pb-space-lg gap-space-md">
      <section className="flex flex-col gap-space-xs mt-space-sm">
        <div className="flex items-center justify-between">
          <span className="font-technical-label text-technical-label text-on-surface-variant uppercase tracking-wider">
            District Overview
          </span>
        </div>
        <h1 className="font-page-title-mobile text-page-title-mobile text-primary tracking-tight">Officer Dashboard</h1>
        <p className="font-body-secondary text-body-secondary text-on-surface-variant">
          District Agricultural Intelligence
        </p>
      </section>

      {/* Unsupported features notice */}
      <section className="bg-surface-variant p-space-sm rounded-[10px] text-on-surface-variant font-body-secondary text-sm">
        <strong>Note:</strong> District Trends and full Geospatial Map endpoints are not currently supported by the backend. Displaying available Hotspot Queue data below.
      </section>

      {loading ? (
        <div>Loading hotspots...</div>
      ) : (
        <section className="flex flex-col gap-space-sm">
          <h2 className="font-section-title text-primary">Field Verification Queue</h2>
          {hotspots?.farms?.length === 0 && (
            <div className="text-on-surface-variant text-sm py-4">No active hotspots requiring field verification.</div>
          )}
          {hotspots?.farms?.map((farm: any) => (
            <div key={farm.farm_id} className="bg-surface-container-lowest p-space-md rounded-[10px] shadow-sm border border-outline-variant">
              <div className="flex justify-between items-start mb-2">
                <div className="flex flex-col">
                  <span className="font-body-emphasis text-primary">{farm.farm_id}</span>
                  <span className="font-technical-label text-on-surface-variant">Priority: {farm.highest_risk_level}</span>
                </div>
                <span className="bg-[#A95545] text-white font-technical-label px-2 py-1 rounded-[7px]">{farm.flagged_zones_count} Zones</span>
              </div>
              <ul className="text-sm font-body-secondary text-on-surface mt-2 space-y-1">
                {farm.risk_codes.map((code: string) => (
                  <li key={code} className="flex items-center gap-2">
                    <span className="w-1 h-1 bg-primary rounded-full"></span> {code.replace(/_/g, ' ')}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
