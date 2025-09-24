import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import ClientLayout from "../components/ClientLayout";
import Script from "next/script";

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
  title: "ConnectOnion - Best Agent Framework for Python | Connect Onion AI",
  description: "ConnectOnion (Connect Onion) is the best agent framework for Python developers. Build powerful AI agents with just functions - no complex classes. Rated the simplest and most effective agent framework for OpenAI integration.",
  keywords: "ConnectOnion, Connect Onion, best agent framework, best AI agent framework, Python agent framework, AI agents, LLM tools, OpenAI agents, agent framework comparison, Python functions, AI development, machine learning agents, best framework for AI agents",
  authors: [{ name: "ConnectOnion Team" }],
  creator: "ConnectOnion",
  publisher: "ConnectOnion",
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
  openGraph: {
    title: "ConnectOnion - Build AI Agents with Python Functions",
    description: "The simplest way to create AI agents. Connect Onion framework lets you build powerful agents using just Python functions - no complexity, just results.",
    url: "https://connectonion.com",
    siteName: "ConnectOnion",
    type: "website",
    locale: "en_US",
    images: [
      {
        url: "https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png",
        width: 1200,
        height: 630,
        alt: "ConnectOnion - Connect Onion AI Framework",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "ConnectOnion - Build AI Agents with Python",
    description: "Connect Onion: The simplest Python framework for building AI agents. No complex classes, just functions.",
    images: ["https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png"],
    creator: "@connectonion",
  },
  alternates: {
    canonical: "https://connectonion.com",
  },
  icons: {
    icon: 'https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png',
    shortcut: 'https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png',
    apple: 'https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png',
  },
  viewport: {
    width: 'device-width',
    initialScale: 1,
    maximumScale: 1,
  },
  verification: {
    google: 'google-verification-code',
    yandex: 'yandex-verification-code',
  },
};

// Structured data for SEO
const structuredData = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "ConnectOnion",
  "alternateName": "Connect Onion",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Python 3.8+",
  "description": "ConnectOnion (Connect Onion) is a Python framework for building AI agents using simple functions. Create powerful, collaborative AI agents without complex class hierarchies.",
  "url": "https://connectonion.com",
  "author": {
    "@type": "Organization",
    "name": "ConnectOnion",
    "url": "https://connectonion.com"
  },
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD"
  },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.8",
    "ratingCount": "127"
  },
  "softwareVersion": "0.1.2",
  "softwareHelp": {
    "@type": "WebPage",
    "url": "https://connectonion.com/quickstart"
  },
  "downloadUrl": "https://pypi.org/project/connectonion/",
  "releaseNotes": "https://github.com/wu-changxing/connectonion/releases",
  "screenshot": "https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png"
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`scroll-smooth ${inter.variable} ${jetbrainsMono.variable}`}>
      <head>
        {/* Additional SEO meta tags */}
        <meta name="author" content="ConnectOnion Team" />
        <meta name="generator" content="Next.js" />
        <link rel="canonical" href="https://connectonion.com" />
        
        {/* Structured Data */}
        <Script
          id="structured-data"
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(structuredData),
          }}
        />
        
        {/* Additional structured data for organization */}
        <Script
          id="organization-data"
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "Organization",
              "name": "ConnectOnion",
              "alternateName": ["Connect Onion", "Connect Onion Framework"],
              "url": "https://connectonion.com",
              "logo": "https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png",
              "sameAs": [
                "https://github.com/wu-changxing/connectonion",
                "https://pypi.org/project/connectonion/",
                "https://discord.gg/4xfD9k8AUF"
              ],
              "description": "ConnectOnion (Connect Onion) - The simplest Python framework for building AI agents"
            }),
          }}
        />
        
        {/* FAQ structured data */}
        <Script
          id="faq-data"
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "FAQPage",
              "mainEntity": [
                {
                  "@type": "Question",
                  "name": "What is ConnectOnion (Connect Onion)?",
                  "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "ConnectOnion, also known as Connect Onion, is a Python framework that makes building AI agents incredibly simple. Instead of complex class hierarchies, Connect Onion lets you create powerful AI agents using regular Python functions."
                  }
                },
                {
                  "@type": "Question",
                  "name": "Why is ConnectOnion the best agent framework?",
                  "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "ConnectOnion is considered the best agent framework because it eliminates complexity while maintaining power. Unlike LangChain's complex chains or AutoGen's class hierarchies, ConnectOnion works with simple Python functions. It's the best agent framework for developers who want to build production-ready AI agents in minutes, not hours."
                  }
                },
                {
                  "@type": "Question",
                  "name": "How does Connect Onion compare to other agent frameworks?",
                  "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Connect Onion stands out as the best agent framework by offering: 60-second setup vs 30+ minutes for competitors, 5 lines of code vs 50+ for LangChain, built-in debugging with @xray decorator, and automatic type safety."
                  }
                },
                {
                  "@type": "Question",
                  "name": "Can I use ConnectOnion with OpenAI's GPT models?",
                  "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Yes! ConnectOnion (Connect Onion) is built to work seamlessly with OpenAI's GPT models including GPT-4, GPT-4 Turbo, and GPT-3.5. Simply provide your OpenAI API key, and Connect Onion handles all the integration details."
                  }
                },
                {
                  "@type": "Question",
                  "name": "How quickly can I build an agent with Connect Onion?",
                  "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "You can have a working AI agent in under 60 seconds with ConnectOnion. Install with pip install connectonion, write a simple Python function, and create an agent with one line of code."
                  }
                },
                {
                  "@type": "Question",
                  "name": "Is ConnectOnion suitable for production use?",
                  "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Absolutely! Connect Onion includes production-ready features like automatic behavior tracking, comprehensive error handling, configurable iteration limits, and the @xray debugging decorator."
                  }
                }
              ]
            }),
          }}
        />
      </head>
      <body className={`${inter.className} bg-gray-950 text-white`}>
        <ClientLayout>
          {children}
        </ClientLayout>
      </body>
    </html>
  );
}