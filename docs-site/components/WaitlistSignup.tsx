'use client'

import { useState } from 'react'
import { Check, Mail, Users, TrendingUp, Calendar, ChevronRight } from 'lucide-react'

interface WaitlistStats {
  totalSignups: number
  todaySignups: number
  weekSignups: number
}

export function WaitlistSignup() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [position, setPosition] = useState<number | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setStatus('loading')

    try {
      const response = await fetch('/api/waitlist', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email }),
      })

      const data = await response.json()

      if (response.ok) {
        setStatus('success')
        setMessage(data.message)
        setPosition(data.stats.position)
        setEmail('')
      } else {
        setStatus('error')
        setMessage(data.error || 'An error occurred')
      }
    } catch (error) {
      setStatus('error')
      setMessage('Failed to join waitlist. Please try again.')
    }
  }

  if (status === 'success') {
    return (
      <div className="bg-gradient-to-r from-green-900/20 to-emerald-900/20 border border-green-500/30 rounded-xl p-8 text-center">
        <div className="w-16 h-16 bg-green-600 rounded-full flex items-center justify-center mx-auto mb-4">
          <Check className="w-8 h-8 text-white" />
        </div>
        <h3 className="text-2xl font-bold text-white mb-2">You're In! 🎉</h3>
        <p className="text-green-200 mb-4">{message}</p>
        {position && (
          <div className="bg-green-800/30 rounded-lg p-4 mb-4">
            <p className="text-green-100">
              <span className="font-semibold">Position #{position}</span> in the waitlist
            </p>
          </div>
        )}
        <p className="text-sm text-green-300">
          We'll notify you when ConnectOnion 0.1.0 is ready with agent-to-agent features!
        </p>
      </div>
    )
  }

  return (
    <div className="bg-gradient-to-r from-purple-900/20 to-pink-900/20 border border-purple-500/30 rounded-xl p-8">
      <div className="text-center mb-6">
        <div className="w-16 h-16 bg-purple-600 rounded-full flex items-center justify-center mx-auto mb-4">
          <Mail className="w-8 h-8 text-white" />
        </div>
        <h3 className="text-2xl font-bold text-white mb-2">Join the Waitlist</h3>
        <p className="text-purple-200 mb-4">
          Be the first to know when we release <strong>v0.1.0</strong> with agent-to-agent protocol features
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email address"
              required
              disabled={status === 'loading'}
              className="w-full px-4 py-3 bg-gray-900 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent disabled:opacity-50"
            />
          </div>
          <button
            type="submit"
            disabled={status === 'loading'}
            className="px-8 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 disabled:from-gray-600 disabled:to-gray-700 text-white font-semibold rounded-lg transition-all duration-300 shadow-lg hover:shadow-xl disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {status === 'loading' ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                Joining...
              </>
            ) : (
              <>
                Join Waitlist
                <ChevronRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>

        {status === 'error' && (
          <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-3">
            <p className="text-red-200 text-sm">{message}</p>
          </div>
        )}
      </form>

      <div className="mt-6 grid grid-cols-3 gap-4 pt-6 border-t border-purple-500/20">
        <div className="text-center">
          <div className="flex items-center justify-center mb-2">
            <Users className="w-5 h-5 text-purple-400" />
          </div>
          <div className="text-sm text-gray-400">Early Access</div>
          <div className="text-lg font-semibold text-white">Priority</div>
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center mb-2">
            <TrendingUp className="w-5 h-5 text-purple-400" />
          </div>
          <div className="text-sm text-gray-400">Beta Features</div>
          <div className="text-lg font-semibold text-white">First Look</div>
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center mb-2">
            <Calendar className="w-5 h-5 text-purple-400" />
          </div>
          <div className="text-sm text-gray-400">Launch Date</div>
          <div className="text-lg font-semibold text-white">Q1 2025</div>
        </div>
      </div>

      <div className="mt-4 text-center">
        <p className="text-xs text-gray-500">
          No spam, unsubscribe anytime. Just the important updates.
        </p>
      </div>
    </div>
  )
}