export default function TopNav() {
  return (
    <header className="fixed top-0 w-full z-50 bg-surface/90 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.04)] pt-safe">
      <div className="h-16 px-margin flex items-center justify-between gap-space-sm">
        <div className="flex items-center gap-space-sm min-w-0">
          <img 
            alt="FARMIGLE Logo" 
            className="h-8 w-auto object-contain flex-shrink-0" 
            src="/logo.png" 
          />
          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-space-xs">
              <span className="font-body-emphasis text-body-emphasis text-primary truncate leading-tight">FARMIGLE</span>
              <span className="font-technical-label text-technical-label text-secondary bg-surface-container-high px-space-xs py-[1px] rounded font-medium">NETWORK</span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-space-sm flex-shrink-0">
          <button 
            type="button"
            aria-label="Change Language" 
            className="h-7 px-space-sm rounded-full bg-surface-container flex items-center justify-center gap-1 font-technical-label text-technical-label text-on-surface hover:bg-surface-container-high transition-colors" 
          >
            <span className="font-body-emphasis text-primary">EN</span>
            <span className="text-outline-variant">|</span>
            <span className="">தமிழ்</span>
          </button>
          <img 
            alt="Profile" 
            className="w-8 h-8 rounded-full object-cover ring-1 ring-surface-variant" 
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuAPv8pJZNrmY_eaRtKSIwNeCVnXbfXc7sqK1LRaSeqe3ODAdRvlz7gzclbdzQKws_maUuQFrYseyodx66vYNdZFrAI00sktd0dT0UOgxDEgYqRX3aCO_OIpennIpMgSVcjd_b15Tx945e2ovgTwLvK2bkklor6gttC8dFbr9jtT-3G9rP2qqzYD2tYVEFQQpV8jn0XYhS24T4iGyWxy2xALjIce4C9i0B-LSTIwF03xCUMwXMzeLWFuMg" 
          />
        </div>
      </div>
    </header>
  );
}
