/**
 * @purpose Shared SEO metadata configuration for ConnectOnion documentation site
 * @context Exported metadata object used across pages for consistent SEO settings
 * @llm-note Provides OpenGraph, Twitter cards, canonical URLs, and structured data for search engines,
 *           includes comprehensive keyword optimization for "ConnectOnion" and "Connect Onion" branding
 */
import type { Metadata } from "next";

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