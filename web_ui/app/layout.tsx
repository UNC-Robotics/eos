import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { ClientLayout } from '@/components/layout/ClientLayout';
import { UserProvider, type CurrentUser } from '@/contexts/UserContext';
import { getSessionUser } from '@/lib/auth/session';
import { rolesFor, isSuperuser } from '@/lib/auth/authz';
import { env } from '@/lib/env';

async function loadCurrentUser(): Promise<CurrentUser | null> {
  const user = await getSessionUser();
  if (!user) return null;
  const roles = await rolesFor(user.sub);
  return { ...user, superuser: isSuperuser(roles), roles, authEnabled: env.AUTH_ENABLED };
}

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
  description: 'Visual graph editor and protocol orchestration system for robotics and automation',
  keywords: ['protocol', 'orchestration', 'robotics', 'automation', 'workflow', 'editor'],
  authors: [{ name: 'EOS Team' }],
  creator: 'EOS Team',
  openGraph: {
    type: 'website',
    locale: 'en_US',
    siteName: 'EOS',
    title: 'EOS - Experiment Orchestration System',
    description: 'Visual graph editor and protocol orchestration system for robotics and automation',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'EOS - Experiment Orchestration System',
    description: 'Visual graph editor and protocol orchestration system for robotics and automation',
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const user = await loadCurrentUser();

  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <UserProvider user={user}>
          <ClientLayout>{children}</ClientLayout>
        </UserProvider>
      </body>
    </html>
  );
}
