import { Link } from 'react-router-dom';
import type { ZoneResult } from '../../types';

interface FarmDigitalTwinProps {
  zones: ZoneResult[];
}

export default function FarmDigitalTwin({ zones }: FarmDigitalTwinProps) {
  const getZoneColor = (zone: ZoneResult) => {
    if (zone.status === 'NO_DATA') return 'bg-surface-variant text-on-surface-variant border-dashed border-2 border-outline'; // No data
    if (zone.health_status === 'unhealthy') return 'bg-[#A95545] text-white'; // Critical health
    if (zone.status === 'NEAR_READY' || zone.status === 'READY') return 'bg-[#3F7658] text-white'; // Ripeness ready/near
    if (zone.risk_level === 'high') return 'bg-[#B68A3A] text-white'; // High risk (weather/satellite)
    return 'bg-[#E8F3ED] text-primary border border-[#d5e8de]'; // Default analyzed healthy
  };

  const getZoneText = (zone: ZoneResult) => {
    if (zone.status === 'NO_DATA') return 'No Evidence';
    if (zone.status === 'NEAR_READY') return `Score: ${(zone.ripeness_score! * 100).toFixed(0)}`;
    if (zone.status === 'READY') return 'Ready';
    if (zone.health_status === 'unhealthy') return 'Unhealthy';
    if (zone.risk_level === 'high') return 'High Risk';
    return 'Analyzed';
  };

  return (
    <section className="w-full bg-surface-container-lowest rounded-[10px] shadow-sm overflow-hidden flex flex-col mt-4">
      <div className="p-space-sm bg-surface-container-high flex items-center justify-between text-on-surface-variant">
        <div className="flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[16px] text-primary">satellite_alt</span>
          <span className="font-technical-label text-technical-label text-primary font-medium tracking-wider">
            SYNCED VIA SENTINEL-2
          </span>
        </div>
        <span className="font-technical-label text-technical-label text-on-surface-variant font-mono text-[10px]">
          10°01'42"N 78°02'15"E
        </span>
      </div>

      <div className="relative w-full bg-surface-container p-2.5 select-none overflow-hidden min-h-[300px]">
        {/* Placeholder background SVG for layout */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-40" xmlns="http://www.w3.org/2000/svg">
          <path d="M 10 30 Q 90 60, 180 40 T 360 70" fill="none" stroke="#42655a" strokeDasharray="4 3" strokeWidth="2"></path>
          <path d="M 140 40 L 140 280" fill="none" stroke="#42655a" strokeWidth="1.5"></path>
          <path d="M 70 45 L 70 270" fill="none" stroke="#42655a" strokeDasharray="2 2" strokeWidth="1"></path>
          <path d="M 220 50 L 220 280" fill="none" stroke="#42655a" strokeDasharray="2 2" strokeWidth="1"></path>
          <path d="M 290 60 L 290 275" fill="none" stroke="#42655a" strokeDasharray="2 2" strokeWidth="1"></path>
        </svg>

        <div className="relative z-10 grid grid-cols-4 gap-1.5 w-full">
          {zones.map((zone) => {
            const colorClass = getZoneColor(zone);
            const isNoData = zone.status === 'NO_DATA';
            return (
              <Link 
                to={`/zones/${zone.zone_id}`}
                key={zone.zone_id}
                className={`flex flex-col justify-between p-1.5 rounded-[7px] text-left transition-colors h-16 ${
                  isNoData ? 'bg-white border-dashed border border-outline-variant hover:bg-surface-container-lowest' 
                           : `${colorClass.split(' ')[0]}/90 hover:${colorClass.split(' ')[0]}`
                }`} 
              >
                <div className="flex items-center justify-between w-full">
                  <span className={`font-technical-label text-[10px] font-semibold ${isNoData ? 'text-outline' : colorClass.includes('text-white') ? 'text-white' : 'text-primary'}`}>
                    {zone.zone_label || zone.zone_id.replace('zone_', 'Z-')}
                  </span>
                  {!isNoData && (
                    <span className={`w-2 h-2 rounded-full ${colorClass.includes('text-white') ? 'bg-white' : 'bg-primary'}`}></span>
                  )}
                </div>
                <span className={`font-technical-label text-[9px] truncate capitalize ${isNoData ? 'text-outline' : colorClass.includes('text-white') ? 'text-white/90' : 'text-primary/90'}`}>
                  {getZoneText(zone)}
                </span>
              </Link>
            );
          })}
        </div>
      </div>

      <div className="p-space-sm bg-surface-container-low flex items-center justify-around font-technical-label text-[10px] text-on-surface-variant flex-wrap gap-1">
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-[#3F7658]"></span>
          <span>Ready/Near</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-[#B68A3A]"></span>
          <span>High Risk</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full border border-outline-variant border-dashed"></span>
          <span>No Evidence</span>
        </div>
      </div>
    </section>
  );
}
