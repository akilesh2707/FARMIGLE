import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { fetchFarms } from '../api/farms';
import { Link } from 'react-router-dom';

import { formatZoneName } from '../utils/zone';

export default function ActionsPage() {
  const [recommendations, setRecommendations] = useState<any[]>([]);
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
        const res = await api.get<{recommendations: any[]}>(`/farms/${farmId}/recommendations`);
        setRecommendations(res.recommendations || []);
      } catch (err) {
        console.error('Failed to load actions', err);
        setErrorMsg('Failed to load actions.');
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  if (loading) return <div className="p-margin">Loading actions...</div>;
  if (errorMsg) return <div className="p-margin text-error">{errorMsg}</div>;

  return (
    <div className="flex flex-col w-full px-margin pb-space-lg gap-space-md">
      <div className="mt-space-sm flex flex-col gap-1">
        <h1 className="text-[28px] font-medium text-primary tracking-tight leading-tight">Priority Actions</h1>
        <p className="text-[14px] text-on-surface-variant font-body-secondary">
          AI-generated interventions for your orchard.
        </p>
      </div>
      
      <div className="flex flex-col gap-4 mt-2">
        {recommendations.length === 0 ? (
          <div className="p-margin bg-[#FAFDFB] border border-surface-variant rounded-[12px] text-center text-on-surface-variant font-body-default shadow-sm">
            No pending actions or recommendations available right now.
          </div>
        ) : (
          recommendations.map((rec, i) => (
            <Link to={`/zones/${rec.zone_id}`} key={i} className="bg-white border border-surface-variant rounded-[12px] overflow-hidden flex flex-col shadow-sm hover:shadow-md transition-shadow">
              {/* Header */}
              <div className={`p-3 border-b border-surface-variant flex justify-between items-center ${
                rec.action.includes('HARVEST') ? 'bg-[#E8F3ED]' : 
                rec.action.includes('CAPTURE') ? 'bg-[#F1F5F3]' : 'bg-[#FAF5E6]'
              }`}>
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-white flex items-center justify-center text-primary shadow-sm border border-black/5">
                    <span className="material-symbols-outlined text-[18px]">
                      {rec.action.includes('HARVEST') ? 'eco' : rec.action.includes('CAPTURE') ? 'photo_camera' : 'build'}
                    </span>
                  </div>
                  <span className="font-technical-label text-[12px] text-primary font-bold tracking-wider uppercase">
                    {formatZoneName(rec.zone_id)}
                  </span>
                </div>
                <span className={`font-technical-label text-[10px] px-2 py-1 rounded-[6px] uppercase font-bold ${
                  rec.action.includes('HARVEST') ? 'bg-[#3F7658] text-white' : 
                  'bg-white text-primary border border-surface-variant shadow-sm'
                }`}>
                  {rec.action.replace(/_/g, ' ')}
                </span>
              </div>
              
              {/* Body */}
              <div className="p-4 flex flex-col gap-2 bg-[#FAFDFB]">
                <h3 className="text-[15px] font-medium text-primary leading-snug">
                  {rec.parts?.recommendation || rec.action.replace(/_/g, ' ')}
                </h3>
                <p className="text-[14px] text-on-surface-variant leading-relaxed">
                  {rec.parts?.explanation || rec.text || 'No detailed explanation available.'}
                </p>
                
                {/* Footer Badges */}
                <div className="mt-2 flex flex-wrap gap-2">
                  {rec.reason_codes?.map((code: string, idx: number) => (
                    <span key={idx} className="font-technical-label text-[10px] tracking-wide text-secondary bg-surface-container-high px-2 py-1 rounded-[4px] uppercase border border-surface-variant">
                      {code.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
