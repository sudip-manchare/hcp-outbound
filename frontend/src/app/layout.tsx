import type { Metadata, Viewport } from 'next';
import { GeistSans } from 'geist/font/sans';
import { GeistMono } from 'geist/font/mono';
import './globals.css';

export const metadata: Metadata = {
  title: 'FalsePay — AI Sunshine Dispute Advocate',
  description:
    'HCP Outbound Engagement Engine: CMS Open Payments Audit & Defense Guard powered by Tiger Data, TimescaleDB, and pgvector.',
  robots: 'noindex',
};

export const viewport: Viewport = {
  colorScheme: 'dark',
  themeColor: '#071720',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
      style={{ colorScheme: 'dark' }}
    >
      <head>
        <meta name="color-scheme" content="dark" />
      </head>
      <body className={GeistSans.className}>{children}</body>
    </html>
  );
}
