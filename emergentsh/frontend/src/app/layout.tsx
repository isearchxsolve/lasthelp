import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Emergent.sh Clone - Build Apps with AI',
  description: 'An agentic AI platform that builds full-stack applications from natural language descriptions',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} antialiased dark:bg-dark-900 dark:text-white`}>
        {children}
      </body>
    </html>
  );
}