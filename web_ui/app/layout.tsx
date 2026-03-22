import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { ClientLayout } from '@/components/layout/ClientLayout';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: {
    default: 'EOS - Experiment Orchestration System',
    template: '%s - EOS',
  },
  description: 'Visual graph editor and experiment orchestration system for robotics and automation',
  keywords: ['experiment', 'orchestration', 'robotics', 'automation', 'workflow', 'editor'],
  authors: [{ name: 'EOS Team' }],
  creator: 'EOS Team',
  openGraph: {
    type: 'website',
    locale: 'en_US',
    siteName: 'EOS',
    title: 'EOS - Experiment Orchestration System',
    description: 'Visual graph editor and experiment orchestration system for robotics and automation',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'EOS - Experiment Orchestration System',
    description: 'Visual graph editor and experiment orchestration system for robotics and automation',
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <ClientLayout>{children}</ClientLayout>
      </body>
    </html>
  );
}
