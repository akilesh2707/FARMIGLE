import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api/client';
import { fetchFarms } from '../api/farms';
import type { ZoneResult } from '../types';
import { formatZoneName } from '../utils/zone';

export default function ZoneDetail() {
  const { zoneId } = useParams<{ zoneId: string }>();
  const [zone, setZone] = useState<ZoneResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!zoneId) return;
    
    const fetchZone = async () => {
      try {
        const farmsList = await fetchFarms();
        if (!farmsList.farms || farmsList.farms.length === 0) throw new Error('No farms');
        const farmId = farmsList.farms[0].farm_id;
        
        const health = await api.get<{ zones: ZoneResult[] }>(`/farms/${farmId}/health`);
        const zoneData = health.zones.find(z => z.zone_id === zoneId);
        
        if (zoneData) {
          setZone(zoneData);
        } else {
          throw new Error('Zone intelligence not found');
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchZone();
  }, [zoneId]);

  if (loading) return <div className="p-margin">Loading zone intelligence...</div>;
  if (!zone) return <div className="p-margin text-error">Zone data not found.</div>;

  return (
    <div className="flex flex-col w-full px-margin pb-space-lg gap-space-md">
      {/* Back Header */}
      <div className="mt-space-sm flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Link to="/" className="flex items-center justify-center">
            <span className="material-symbols-outlined text-[24px] text-primary">arrow_back</span>
          </Link>
          <h1 className="text-[22px] font-medium text-primary tracking-tight">Zone Telemetry Detail</h1>
        </div>
      </div>

      {/* Main Image Header Card */}
      <div className="w-full bg-gradient-to-br from-[#1A3329] to-[#365A4B] rounded-t-[12px] p-4 flex flex-col justify-between h-[180px] relative overflow-hidden">
        {/* Placeholder SVG background pattern */}
        <svg className="absolute inset-0 w-full h-full opacity-20 pointer-events-none" xmlns="http://www.w3.org/2000/svg">
          <pattern id="topo" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M0,20 Q10,5 20,20 T40,20" fill="none" stroke="white" strokeWidth="1"/>
            <path d="M0,40 Q10,25 20,40 T40,40" fill="none" stroke="white" strokeWidth="1"/>
          </pattern>
          <rect width="100%" height="100%" fill="url(#topo)" />
        </svg>

        <div className="relative z-10 flex justify-between items-start">
          <span className="font-technical-label text-[10px] tracking-wider bg-white text-primary px-2 py-1 rounded-full uppercase shadow-sm">
            {zone.status === 'NO_DATA' ? 'No Data' : zone.status.replace('_', ' ')}
          </span>
          <span className="font-technical-label text-[10px] tracking-wider bg-black/40 text-white backdrop-blur-sm px-2 py-1 rounded-full flex items-center gap-1 border border-white/20 shadow-sm">
            <span className="material-symbols-outlined text-[12px]">schedule</span>
            {zone.estimated_harvest_window ? `Window ${zone.estimated_harvest_window}` : 'Pending Evidence'}
          </span>
        </div>
        
        <div className="relative z-10 flex justify-between items-end mt-auto">
          <div className="flex flex-col">
            <span className="font-technical-label text-[10px] tracking-wider text-white/80 uppercase">
              {zone.zone_label ? `SECTOR ${zone.zone_label}` : 'FARM SECTOR'}
            </span>
            <h2 className="text-[32px] font-bold text-white leading-none tracking-tight">
              {formatZoneName(zone.zone_id, zone.zone_label).toUpperCase()}
            </h2>
          </div>
          <button className="bg-[#487E66] text-white px-3 py-1.5 rounded-[6px] font-medium text-[12px] flex items-center gap-1 shadow-sm border border-white/20" type="button">
            <span className="material-symbols-outlined text-[14px]">check</span>
            {zone.recommended_action ? zone.recommended_action.replace(/_/g, ' ') : 'Prioritize'}
          </button>
        </div>
      </div>
      
      {/* Status Bar */}
      <div className="bg-surface-container-low px-4 py-3 rounded-b-[12px] border border-surface-variant flex items-center justify-between shadow-sm text-[10px] font-technical-label tracking-wider text-primary uppercase">
        <span>Priority: {zone.risk_level}</span>
        <span>•</span>
        <span>Status: {zone.status.replace('_', ' ')}</span>
      </div>

      {/* 3 Metrics */}
      <section className="grid grid-cols-3 gap-2 mt-2">
        <div className="bg-white p-3 rounded-[10px] shadow-sm flex flex-col justify-between border border-surface-variant">
          <span className="font-technical-label text-[10px] text-on-surface-variant uppercase tracking-wider">Ripeness</span>
          <div className="my-1 text-[26px] font-bold text-primary leading-none tracking-tight">
            {zone.ripeness_score !== undefined && zone.ripeness_score !== null ? (zone.ripeness_score * 100).toFixed(0) + '%' : 'N/A'}
          </div>
          <div className="w-full bg-surface-variant h-1 rounded-full overflow-hidden mt-1">
            <div className="bg-[#3F7658] h-full" style={{ width: zone.ripeness_score ? `${zone.ripeness_score * 100}%` : '0%' }}></div>
          </div>
        </div>
        <div className="bg-white p-3 rounded-[10px] shadow-sm flex flex-col justify-between border border-surface-variant">
          <span className="font-technical-label text-[10px] text-on-surface-variant uppercase tracking-wider">Health</span>
          <div className="my-1 text-[26px] font-bold text-primary leading-none tracking-tight capitalize">
            {zone.health_status === 'unknown' ? 'Unk' : zone.health_status}
          </div>
          <div className="w-full bg-surface-variant h-1 rounded-full overflow-hidden mt-1">
            <div className={`h-full ${zone.health_status === 'healthy' ? 'bg-[#3F7658]' : 'bg-[#1A3329]'}`} style={{ width: '100%' }}></div>
          </div>
        </div>
        <div className="bg-white p-3 rounded-[10px] shadow-sm flex flex-col justify-between border border-surface-variant">
          <span className="font-technical-label text-[10px] text-on-surface-variant uppercase tracking-wider">Confidence</span>
          <div className="my-1 text-[26px] font-bold text-primary leading-none tracking-tight">
            {zone.confidence ? (zone.confidence * 100).toFixed(0) + '%' : 'N/A'}
          </div>
          <div className="w-full bg-surface-variant h-1 rounded-full overflow-hidden mt-1">
            <div className="bg-[#1A3329] h-full" style={{ width: zone.confidence ? `${zone.confidence * 100}%` : '0%' }}></div>
          </div>
        </div>
      </section>

      {/* Rationale Section */}
      <section className="bg-white rounded-[12px] border border-surface-variant shadow-sm overflow-hidden mt-2">
        <div className="p-4 border-b border-surface-variant flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-[#183C32]"></div>
          <h3 className="font-technical-label text-[12px] tracking-wider text-primary font-medium">WHY THIS RECOMMENDATION?</h3>
        </div>
        <div className="p-4 flex flex-col gap-3 bg-[#FAFDFB]">
          <div className="bg-[#E8F3ED] p-3 rounded-[8px]">
            <span className="font-technical-label text-[10px] text-secondary uppercase tracking-wider">Recommendation</span>
            <p className="mt-1 font-medium text-primary text-[14px]">
              {zone.recommended_action ? zone.recommended_action.replace(/_/g, ' ') : 'N/A'}
            </p>
          </div>
          <div className="bg-[#F1F5F3] p-3 rounded-[8px]">
            <span className="font-technical-label text-[10px] text-on-surface-variant uppercase tracking-wider">Explanation</span>
            <p className="mt-1 text-on-surface text-[14px] leading-snug">
              {zone.reason_codes && zone.reason_codes.length > 0 
                ? zone.reason_codes.map(rc => rc.replace(/_/g, ' ')).join(', ') 
                : 'No specific rationale provided.'}
            </p>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-2 mt-4">
        <Link 
          to="/actions" 
          className="w-full h-12 bg-[#E8F3ED] text-[#183C32] hover:bg-[#d5e8de] rounded-[8px] font-medium text-[14px] flex items-center justify-center gap-2 transition-colors border border-[#d5e8de]"
        >
          <span className="material-symbols-outlined text-[20px]">groups</span>
          <span>View Actions</span>
        </Link>
        <Link 
          to="/analyze" 
          className="w-full h-12 bg-white text-primary border border-surface-variant hover:bg-surface-container-lowest rounded-[8px] font-medium text-[14px] flex items-center justify-center gap-2 transition-colors"
        >
          <span className="material-symbols-outlined text-[20px]">photo_camera</span>
          <span>Log Observation</span>
        </Link>
      </div>
    </div>
  );
}
