import { Link, useLocation } from 'react-router-dom';

export default function BottomNav() {
  const location = useLocation();

  const navItems = [
    { path: '/', icon: 'space_dashboard', label: 'Home' },
    { path: '/map', icon: 'map', label: 'Map' },
    { path: '/analyze', icon: 'photo_camera', label: 'Analyze' },
    { path: '/ask', icon: 'mic', label: 'Ask Farmigle' },
    { path: '/actions', icon: 'fact_check', label: 'Actions' },
  ];

  return (
    <nav className="fixed bottom-0 w-full z-50 pb-safe bg-surface/90 backdrop-blur-xl shadow-[0_-1px_8px_rgba(0,0,0,0.04)]">
      <div className="flex items-center justify-around h-16 px-space-xs">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex flex-col items-center justify-center min-w-[56px] min-h-[44px] py-1 transition-colors ${
                isActive ? 'text-primary font-body-emphasis' : 'text-on-surface-variant hover:text-primary'
              }`}
            >
              <span className="material-symbols-outlined text-[22px]">{item.icon}</span>
              <span className="font-technical-label text-technical-label mt-0.5 truncate">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
