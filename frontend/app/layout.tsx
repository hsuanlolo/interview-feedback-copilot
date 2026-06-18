import type { Metadata } from 'next';
import './globals.css';
import { Navbar } from '@/components/Navbar';

export const metadata: Metadata = {
  title: 'Interview Feedback Copilot',
  description: 'Evidence-grounded interview feedback synthesis. Surfaces evidence. Human decides.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 antialiased min-h-screen">
        <Navbar />
        {children}
      </body>
    </html>
  );
}
