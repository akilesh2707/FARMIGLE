import TopNav from './TopNav';
import BottomNav from './BottomNav';
import { Outlet } from 'react-router-dom';

export default function Layout() {
  return (
    <div className="bg-surface text-on-surface font-body-default text-body-default min-h-screen flex flex-col antialiased selection:bg-secondary-container selection:text-on-secondary-container">
      <TopNav />
      <main className="flex-1 flex flex-col relative w-full pt-16 pb-24 bg-surface min-h-screen">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
