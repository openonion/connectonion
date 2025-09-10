'use client'

import { useState, useEffect } from 'react'
import { 
  Github, MessageCircle, Package, BookOpen, Newspaper, Mail,
  Twitter, Instagram, Youtube, Linkedin, Globe, ExternalLink,
  Copy, Check, Share2, QrCode, Link as LinkIcon, Heart,
  Sparkles, Users, Code, FileText, HelpCircle, Video
} from 'lucide-react'
import Link from 'next/link'
import { ContentNavigation } from '../../components/ContentNavigation'
import QRCode from 'qrcode'

interface LinkItem {
  title: string
  description?: string
  url: string
  icon: React.ElementType
  color: string
  bgColor: string
  borderColor: string
  external?: boolean
  available?: boolean
}

interface LinkSection {
  title: string
  description?: string
  links: LinkItem[]
}

export default function LinksPage() {
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null)
  const [showQR, setShowQR] = useState(false)
  const [qrCodeDataUrl, setQrCodeDataUrl] = useState<string>('')

  useEffect(() => {
    // Generate QR code for the links page URL
    const generateQRCode = async () => {
      try {
        const url = 'https://docs.connectonion.com/links'
        const dataUrl = await QRCode.toDataURL(url, {
          width: 256,
          margin: 1,
          color: {
            dark: '#6B46C1', // Purple color matching the theme
            light: '#FFFFFF'
          },
          errorCorrectionLevel: 'H', // High error correction for logo overlay
        })
        setQrCodeDataUrl(dataUrl)
      } catch (err) {
        console.error('Error generating QR code:', err)
      }
    }
    
    generateQRCode()
  }, [])

  const handleCopyLink = (url: string, title: string) => {
    navigator.clipboard.writeText(url)
    setCopiedUrl(title)
    setTimeout(() => setCopiedUrl(null), 2000)
  }

  const handleSharePage = () => {
    const url = window.location.href
    if (navigator.share) {
      navigator.share({
        title: 'ConnectOnion - All Links',
        text: 'Check out ConnectOnion - Build AI agents with simple, powerful Python code',
        url: url
      })
    } else {
      handleCopyLink(url, 'page')
    }
  }

  const linkSections: LinkSection[] = [
    {
      title: '🚀 Core Platform',
      description: 'Essential ConnectOnion resources',
      links: [
        {
          title: 'GitHub Repository',
          description: 'Source code, issues, and contributions',
          url: 'https://github.com/wu-changxing/connectonion',
          icon: Github,
          color: 'text-white',
          bgColor: 'bg-gradient-to-br from-gray-700 to-gray-900',
          borderColor: 'border-gray-600',
          external: true,
          available: true
        },
        {
          title: 'PyPI Package',
          description: 'Install via pip',
          url: 'https://pypi.org/project/connectonion/',
          icon: Package,
          color: 'text-blue-400',
          bgColor: 'bg-gradient-to-br from-blue-600 to-blue-800',
          borderColor: 'border-blue-500',
          external: true,
          available: true
        },
        {
          title: 'Documentation',
          description: 'Complete guides and API reference',
          url: 'https://docs.connectonion.com',
          icon: BookOpen,
          color: 'text-purple-400',
          bgColor: 'bg-gradient-to-br from-purple-600 to-purple-800',
          borderColor: 'border-purple-500',
          external: true,
          available: true
        }
      ]
    },
    {
      title: '💬 Community',
      description: 'Join our growing community',
      links: [
        {
          title: 'Discord Server',
          description: 'Chat with the community',
          url: 'https://discord.gg/4xfD9k8AUF',
          icon: MessageCircle,
          color: 'text-indigo-400',
          bgColor: 'bg-gradient-to-br from-indigo-600 to-indigo-800',
          borderColor: 'border-indigo-500',
          external: true,
          available: true
        },
        {
          title: 'GitHub Discussions',
          description: 'Ask questions and share ideas',
          url: 'https://github.com/wu-changxing/connectonion/discussions',
          icon: Users,
          color: 'text-green-400',
          bgColor: 'bg-gradient-to-br from-green-600 to-green-800',
          borderColor: 'border-green-500',
          external: true,
          available: true
        }
      ]
    },
    {
      title: '📱 Social Media',
      description: 'Follow us for updates and content',
      links: [
        {
          title: 'Twitter / X',
          description: 'Latest news and updates',
          url: '#',
          icon: Twitter,
          color: 'text-sky-400',
          bgColor: 'bg-gradient-to-br from-sky-600 to-sky-800',
          borderColor: 'border-sky-500',
          external: true,
          available: false
        },
        {
          title: 'YouTube',
          description: 'Video tutorials and demos',
          url: 'https://www.youtube.com/@openonionai',
          icon: Youtube,
          color: 'text-red-400',
          bgColor: 'bg-gradient-to-br from-red-600 to-red-800',
          borderColor: 'border-red-500',
          external: true,
          available: true
        },
        {
          title: 'LinkedIn',
          description: 'Professional updates',
          url: 'https://www.linkedin.com/company/openonion/',
          icon: Linkedin,
          color: 'text-blue-400',
          bgColor: 'bg-gradient-to-br from-blue-700 to-blue-900',
          borderColor: 'border-blue-600',
          external: true,
          available: true
        },
        {
          title: 'Instagram',
          description: 'Behind the scenes',
          url: 'https://www.instagram.com/openonionai/',
          icon: Instagram,
          color: 'text-pink-400',
          bgColor: 'bg-gradient-to-br from-pink-600 to-purple-700',
          borderColor: 'border-pink-500',
          external: true,
          available: true
        },
        {
          title: 'TikTok',
          description: 'Quick tips and demos',
          url: 'https://www.tiktok.com/@closeonion',
          icon: Video,
          color: 'text-pink-400',
          bgColor: 'bg-gradient-to-br from-gray-900 to-pink-900',
          borderColor: 'border-pink-600',
          external: true,
          available: true
        }
      ]
    },
    {
      title: '📚 Resources',
      description: 'Learn and explore',
      links: [
        {
          title: 'Blog',
          description: 'Design decisions and insights',
          url: 'https://docs.connectonion.com/blog',
          icon: Newspaper,
          color: 'text-orange-400',
          bgColor: 'bg-gradient-to-br from-orange-600 to-orange-800',
          borderColor: 'border-orange-500',
          external: true,
          available: true
        },
        {
          title: 'Examples',
          description: 'Sample projects and tutorials',
          url: 'https://docs.connectonion.com/examples',
          icon: Code,
          color: 'text-yellow-400',
          bgColor: 'bg-gradient-to-br from-yellow-600 to-yellow-800',
          borderColor: 'border-yellow-500',
          external: true,
          available: true
        },
        {
          title: 'API Reference',
          description: 'Technical documentation',
          url: 'https://docs.connectonion.com/tools',
          icon: FileText,
          color: 'text-teal-400',
          bgColor: 'bg-gradient-to-br from-teal-600 to-teal-800',
          borderColor: 'border-teal-500',
          external: true,
          available: true
        }
      ]
    },
    {
      title: '🤝 Support',
      description: 'Get help and contribute',
      links: [
        {
          title: 'Report Issues',
          description: 'Bug reports and feature requests',
          url: 'https://github.com/wu-changxing/connectonion/issues',
          icon: HelpCircle,
          color: 'text-amber-400',
          bgColor: 'bg-gradient-to-br from-amber-600 to-amber-800',
          borderColor: 'border-amber-500',
          external: true,
          available: true
        },
        {
          title: 'Email Contact',
          description: 'Reach out directly',
          url: 'mailto:contact@connectonion.com',
          icon: Mail,
          color: 'text-gray-400',
          bgColor: 'bg-gradient-to-br from-gray-600 to-gray-800',
          borderColor: 'border-gray-500',
          external: true,
          available: false
        }
      ]
    }
  ]

  const LinkCard = ({ link }: { link: LinkItem }) => {
    const Icon = link.icon
    const isClickable = link.available && link.url !== '#'
    
    const content = (
      <div className={`
        relative group w-full p-6 rounded-2xl transition-all duration-300 transform
        ${link.bgColor} ${link.borderColor} border-2
        ${isClickable ? 'hover:scale-105 hover:shadow-2xl cursor-pointer' : 'opacity-60 cursor-not-allowed'}
      `}>
        {/* Coming Soon Badge */}
        {!link.available && (
          <div className="absolute -top-2 -right-2 px-3 py-1 bg-gray-800 border border-gray-600 rounded-full">
            <span className="text-xs font-medium text-gray-400">Coming Soon</span>
          </div>
        )}
        
        {/* Content */}
        <div className="flex items-start gap-4">
          <div className={`p-3 rounded-xl bg-white/10 ${link.color}`}>
            <Icon className="w-6 h-6" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-white mb-1 flex items-center gap-2">
              {link.title}
              {link.external && isClickable && (
                <ExternalLink className="w-4 h-4 text-gray-400" />
              )}
            </h3>
            {link.description && (
              <p className="text-sm text-gray-300">{link.description}</p>
            )}
          </div>
        </div>
        
        {/* Copy button */}
        {isClickable && (
          <button
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              handleCopyLink(link.url, link.title)
            }}
            className="absolute top-4 right-4 p-2 rounded-lg bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/20"
            title="Copy link"
          >
            {copiedUrl === link.title ? (
              <Check className="w-4 h-4 text-green-400" />
            ) : (
              <Copy className="w-4 h-4 text-white" />
            )}
          </button>
        )}
      </div>
    )
    
    if (!isClickable) {
      return content
    }
    
    if (link.external) {
      return (
        <a
          href={link.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block"
        >
          {content}
        </a>
      )
    }
    
    return (
      <Link href={link.url} className="block">
        {content}
      </Link>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 via-purple-900/10 to-gray-900">
      <div className="max-w-6xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="text-center mb-12">
          {/* Logo */}
          <div className="flex justify-center mb-6">
            <div className="relative">
              <div className="absolute inset-0 bg-purple-500 blur-xl opacity-50 animate-pulse"></div>
              <img 
                src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" 
                alt="ConnectOnion" 
                className="relative w-24 h-24 rounded-2xl object-cover shadow-2xl"
              />
            </div>
          </div>
          
          {/* Title and Description */}
          <h1 className="text-5xl font-bold text-white mb-4 flex items-center justify-center gap-3">
            <LinkIcon className="w-10 h-10 text-purple-400" />
            ConnectOnion Links
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto mb-8">
            All our platforms and resources in one place. Build AI agents with simple, powerful Python code.
          </p>
          
          {/* Action Buttons */}
          <div className="flex flex-wrap justify-center gap-4">
            <button
              onClick={handleSharePage}
              className="flex items-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors font-medium"
            >
              <Share2 className="w-5 h-5" />
              Share Page
            </button>
            <button
              onClick={() => setShowQR(!showQR)}
              className="flex items-center gap-2 px-6 py-3 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors font-medium"
            >
              <QrCode className="w-5 h-5" />
              QR Code
            </button>
          </div>
          
          {/* QR Code Display */}
          {showQR && qrCodeDataUrl && (
            <div className="mt-8 inline-block animate-fadeIn">
              {/* Outer glow container */}
              <div className="relative">
                {/* Animated gradient background */}
                <div className="absolute inset-0 bg-gradient-to-r from-purple-600 via-pink-600 to-blue-600 rounded-3xl blur-xl opacity-60 animate-pulse"></div>
                
                {/* Main QR code container */}
                <div className="relative bg-gradient-to-br from-gray-900 via-purple-900/20 to-gray-900 p-1 rounded-3xl shadow-2xl">
                  <div className="bg-white rounded-2xl p-6">
                    {/* QR Code with logo overlay */}
                    <div className="relative">
                      <img 
                        src={qrCodeDataUrl}
                        alt="QR Code for ConnectOnion Links" 
                        className="w-64 h-64 rounded-lg"
                      />
                      
                      {/* Center logo overlay */}
                      <div className="absolute inset-0 flex items-center justify-center">
                        <div className="bg-white rounded-xl p-2 shadow-lg">
                          <img 
                            src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png" 
                            alt="ConnectOnion Logo" 
                            className="w-12 h-12 rounded-lg"
                          />
                        </div>
                      </div>
                    </div>
                    
                    {/* Text and icons */}
                    <div className="mt-4 text-center">
                      <div className="flex items-center justify-center gap-2 mb-2">
                        <QrCode className="w-5 h-5 text-purple-600" />
                        <p className="text-lg font-semibold text-gray-800">Scan to Connect</p>
                      </div>
                      <p className="text-sm text-gray-600">
                        docs.connectonion.com/links
                      </p>
                      <div className="mt-3 flex items-center justify-center gap-3">
                        <div className="flex items-center gap-1 text-xs text-gray-500">
                          <Sparkles className="w-3 h-3" />
                          <span>Quick Access</span>
                        </div>
                        <div className="text-gray-300">•</div>
                        <div className="flex items-center gap-1 text-xs text-gray-500">
                          <LinkIcon className="w-3 h-3" />
                          <span>All Links</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                
                {/* Decorative corners */}
                <div className="absolute -top-2 -left-2 w-6 h-6 border-t-2 border-l-2 border-purple-400 rounded-tl-lg"></div>
                <div className="absolute -top-2 -right-2 w-6 h-6 border-t-2 border-r-2 border-purple-400 rounded-tr-lg"></div>
                <div className="absolute -bottom-2 -left-2 w-6 h-6 border-b-2 border-l-2 border-purple-400 rounded-bl-lg"></div>
                <div className="absolute -bottom-2 -right-2 w-6 h-6 border-b-2 border-r-2 border-purple-400 rounded-br-lg"></div>
              </div>
            </div>
          )}
        </div>
        
        {/* Links Sections */}
        <div className="space-y-12">
          {linkSections.map((section, idx) => (
            <div key={idx}>
              <div className="mb-6">
                <h2 className="text-2xl font-bold text-white mb-2">
                  {section.title}
                </h2>
                {section.description && (
                  <p className="text-gray-400">{section.description}</p>
                )}
              </div>
              
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                {section.links.map((link, linkIdx) => (
                  <LinkCard key={linkIdx} link={link} />
                ))}
              </div>
            </div>
          ))}
        </div>
        
        {/* Footer */}
        <div className="mt-16 pt-8 border-t border-gray-700 text-center">
          <p className="text-gray-400 mb-4">
            ConnectOnion is open source and community-driven
          </p>
          <div className="flex items-center justify-center gap-2 text-sm text-gray-500">
            <span>Made with</span>
            <Heart className="w-4 h-4 text-red-500 fill-current" />
            <span>by the ConnectOnion team</span>
          </div>
          <div className="mt-4 flex items-center justify-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-400" />
            <span className="text-sm text-purple-400">
              Add your link? Contact us on Discord!
            </span>
          </div>
        </div>
        
        {/* Navigation */}
        <ContentNavigation />
      </div>
    </div>
  )
}