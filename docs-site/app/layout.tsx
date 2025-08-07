import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { DocsSidebar } from "../components/DocsSidebar";
import { MobileDocsNav } from "../components/MobileDocsNav";
import Footer from "../components/Footer";

const inter = Inter({ 
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({ 
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ConnectOnion Documentation - Build AI Agents with Python Functions",
  description: "Complete documentation for ConnectOnion: The simplest way to create AI agents that can use tools and collaborate. No classes, no complexity.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`scroll-smooth ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className={`${inter.className} bg-gray-950 text-white`}>
        {/* Mobile Documentation Navigation */}
        <MobileDocsNav />
        
        <div className="flex min-h-screen">
          {/* Desktop Sidebar */}
          <div className="hidden lg:block">
            <DocsSidebar />
          </div>
          
          {/* Main Content */}
          <main className="flex-1 min-w-0 flex flex-col">
            <div className="flex-1">
              {children}
            </div>
            <Footer />
          </main>
        </div>
      </body>
    </html>
  );
}