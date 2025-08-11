import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

// Simple in-memory store for development
const WAITLIST_FILE = path.join(process.cwd(), 'waitlist.json')

interface WaitlistEntry {
  email: string
  timestamp: string
  userAgent?: string
  referer?: string
  ip?: string
}

function loadWaitlist(): WaitlistEntry[] {
  try {
    if (fs.existsSync(WAITLIST_FILE)) {
      const data = fs.readFileSync(WAITLIST_FILE, 'utf8')
      return JSON.parse(data)
    }
  } catch (error) {
    console.error('Error loading waitlist:', error)
  }
  return []
}

function saveWaitlist(entries: WaitlistEntry[]): void {
  try {
    fs.writeFileSync(WAITLIST_FILE, JSON.stringify(entries, null, 2))
  } catch (error) {
    console.error('Error saving waitlist:', error)
  }
}

async function sendDiscordNotification(entry: WaitlistEntry, stats: any) {
  const webhookUrl = process.env.DISCORD_WEBHOOK_URL
  if (!webhookUrl) {
    console.error('Discord webhook URL not configured')
    return
  }

  const embed = {
    title: '🎯 New Waitlist Signup!',
    color: 0x7c3aed, // Purple color
    fields: [
      {
        name: '📧 Email',
        value: entry.email,
        inline: true
      },
      {
        name: '🕒 Time',
        value: new Date(entry.timestamp).toLocaleString(),
        inline: true
      },
      {
        name: '🌐 Source',
        value: entry.referer || 'Direct',
        inline: true
      },
      {
        name: '📊 Total Signups',
        value: stats.totalSignups.toString(),
        inline: true
      },
      {
        name: '📈 Today',
        value: stats.todaySignups.toString(),
        inline: true
      },
      {
        name: '📅 This Week',
        value: stats.weekSignups.toString(),
        inline: true
      }
    ],
    footer: {
      text: 'ConnectOnion Waitlist • https://connectonion.com'
    },
    timestamp: entry.timestamp
  }

  try {
    await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        embeds: [embed]
      })
    })
  } catch (error) {
    console.error('Error sending Discord notification:', error)
  }
}

function getStats(entries: WaitlistEntry[]) {
  const now = new Date()
  const today = now.toDateString()
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)

  const todaySignups = entries.filter(entry => 
    new Date(entry.timestamp).toDateString() === today
  ).length

  const weekSignups = entries.filter(entry => 
    new Date(entry.timestamp) > weekAgo
  ).length

  return {
    totalSignups: entries.length,
    todaySignups,
    weekSignups
  }
}

export async function POST(request: NextRequest) {
  try {
    const { email } = await request.json()

    // Validate email
    if (!email || !email.includes('@')) {
      return NextResponse.json(
        { error: 'Valid email address required' },
        { status: 400 }
      )
    }

    // Load existing waitlist
    const waitlist = loadWaitlist()

    // Check if email already exists
    if (waitlist.some(entry => entry.email.toLowerCase() === email.toLowerCase())) {
      return NextResponse.json(
        { error: 'Email already registered' },
        { status: 400 }
      )
    }

    // Create new entry
    const newEntry: WaitlistEntry = {
      email: email.toLowerCase(),
      timestamp: new Date().toISOString(),
      userAgent: request.headers.get('user-agent') || undefined,
      referer: request.headers.get('referer') || undefined,
      ip: request.headers.get('x-forwarded-for') || request.headers.get('x-real-ip') || undefined
    }

    // Add to waitlist
    waitlist.push(newEntry)
    saveWaitlist(waitlist)

    // Get stats and send Discord notification
    const stats = getStats(waitlist)
    await sendDiscordNotification(newEntry, stats)

    return NextResponse.json({
      success: true,
      message: 'Successfully added to waitlist!',
      stats: {
        position: waitlist.length
      }
    })

  } catch (error) {
    console.error('Waitlist signup error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function GET() {
  try {
    const waitlist = loadWaitlist()
    const stats = getStats(waitlist)
    
    return NextResponse.json({
      stats: {
        ...stats,
        recentSignups: waitlist
          .slice(-5)
          .map(entry => ({
            email: entry.email.replace(/(.{2}).*(@.*)/, '$1***$2'), // Mask email
            timestamp: entry.timestamp
          }))
      }
    })
  } catch (error) {
    console.error('Error getting waitlist stats:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}