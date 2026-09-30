import { useState } from 'react';
import { uploadObservation, fetchFarms } from '../api/farms';

export default function PhotoAnalysis() {
  const [preview, setPreview] = useState<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'analyzing' | 'done' | 'error'>('idle');
  const [result, setResult] = useState<any>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result as string);
      };
      reader.readAsDataURL(selectedFile);
    }
  };

  const submitPhoto = async () => {
    if (!preview) return;
    setStatus('analyzing');
    try {
      const farmsList = await fetchFarms();
      if (!farmsList.farms || farmsList.farms.length === 0) {
        setStatus('error');
        return;
      }
      const farmId = farmsList.farms[0].farm_id;
      const base64Data = preview.split(',')[1];
      const payload = {
        source: 'phone',
        image_base64: base64Data
      };
      const response = await uploadObservation(farmId, payload);
      setResult(response);
      setStatus('done');
    } catch (err) {
      console.error(err);
      setStatus('error');
    }
  };

  return (
    <div className="flex flex-col w-full px-margin pb-space-lg gap-space-md">
      <div className="mt-space-sm flex flex-col gap-1">
        <div className="flex items-center gap-2 cursor-pointer" onClick={() => window.history.back()}>
          <span className="material-symbols-outlined text-[24px] text-primary">arrow_back</span>
          <h1 className="text-[22px] font-medium text-primary tracking-tight">Photo Analysis</h1>
        </div>
        <p className="text-[14px] text-on-surface-variant font-body-secondary mt-1">
          Upload an image of the crop or canopy for AI detection and health assessment.
        </p>
      </div>

      {status === 'idle' && (
        <>
          <label className="flex flex-col items-center justify-center w-full h-48 border-2 border-dashed border-[#BCCFC5] rounded-[12px] bg-[#FAFDFB] hover:bg-[#E8F3ED] transition-colors cursor-pointer mt-2 shadow-sm">
            <span className="material-symbols-outlined text-[32px] text-primary mb-2 opacity-80">add_a_photo</span>
            <span className="font-technical-label text-[12px] tracking-wide text-primary">TAP TO SELECT PHOTO</span>
            <input type="file" accept="image/*" className="hidden" onChange={handleFileChange} />
          </label>

          {preview && (
            <div className="mt-4 flex flex-col gap-4">
              <div className="relative rounded-[12px] overflow-hidden border border-surface-variant shadow-sm">
                <img src={preview} alt="Preview" className="w-full h-auto" />
                <div className="absolute top-2 right-2 bg-black/50 backdrop-blur-sm px-2 py-1 rounded text-white text-[10px] font-technical-label tracking-wide">
                  READY
                </div>
              </div>
              <button 
                onClick={submitPhoto}
                className="w-full h-12 bg-[#183C32] hover:bg-[#244F43] active:bg-[#122e26] text-white rounded-[8px] font-medium text-[15px] flex items-center justify-center gap-2 shadow-sm transition-colors"
              >
                <span className="material-symbols-outlined text-[18px]">document_scanner</span>
                <span>Analyze Photo</span>
              </button>
            </div>
          )}
        </>
      )}

      {status === 'analyzing' && (
        <div className="flex flex-col items-center justify-center h-48 bg-[#F1F5F3] rounded-[12px] border border-surface-variant mt-2 shadow-sm">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mb-4"></div>
          <span className="font-technical-label text-[12px] tracking-widest text-primary uppercase">Analyzing Evidence...</span>
        </div>
      )}

      {status === 'done' && result && (
        <div className="bg-white border border-surface-variant p-4 rounded-[12px] shadow-sm flex flex-col gap-3 mt-2">
          <div className="flex items-center gap-2 text-primary font-medium border-b border-surface-variant pb-3">
            <span className="material-symbols-outlined text-[#3F7658]">check_circle</span>
            <h2 className="text-[16px]">Analysis Complete</h2>
          </div>
          <div className="flex flex-col gap-1 mt-1">
            <span className="font-technical-label text-[10px] text-on-surface-variant uppercase tracking-wider">Findings</span>
            {result.observations && result.observations.length > 0 ? (
              <ul className="list-disc pl-5 text-[14px] text-primary space-y-1">
                {result.observations.map((obs: any, i: number) => (
                  <li key={i}>{obs.notes || 'Observation logged.'}</li>
                ))}
              </ul>
            ) : (
              <p className="text-[14px] text-primary">Observation successfully logged.</p>
            )}
          </div>
          <button 
            onClick={() => { setStatus('idle'); setPreview(null); setResult(null); }}
            className="mt-4 w-full h-12 border border-surface-variant hover:bg-[#E8F3ED] text-primary rounded-[8px] font-medium text-[15px] transition-colors"
          >
            Analyze Another
          </button>
        </div>
      )}

      {status === 'error' && (
        <div className="bg-[#FAF5E6] border border-[#EBE3CD] text-[#A95545] p-4 rounded-[12px] mt-2 shadow-sm">
          <div className="flex items-center gap-2 font-medium mb-1">
            <span className="material-symbols-outlined text-[20px]">error</span>
            <span>Analysis Failed</span>
          </div>
          <p className="text-[14px] text-on-surface-variant">Unable to process the photo or connect to the server.</p>
          <button onClick={() => setStatus('idle')} className="mt-4 underline text-[14px] font-medium text-primary">Try Again</button>
        </div>
      )}
    </div>
  );
}
