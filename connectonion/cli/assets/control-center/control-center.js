const BRIDGE_VERSION = 1
let port = null
let revision = null
let sequence = 0
const pending = new Map()

const connection = document.querySelector('#connection')
const connectionLabel = document.querySelector('#connection-label')
const conversationLabel = document.querySelector('#conversation-label')
const status = document.querySelector('#status')
const statusMessage = document.querySelector('#status-message')
const form = document.querySelector('#message-form')
const input = document.querySelector('#message')
const submit = form.querySelector('button[type="submit"]')
const skillList = document.querySelector('#skills')
const skillCount = document.querySelector('#skill-count')
const SVG_NS = 'http://www.w3.org/2000/svg'

function setStatus(message, state = 'idle') {
  status.dataset.state = state
  statusMessage.textContent = message
  const icon = status.querySelector('.status-icon')
  icon.textContent = state === 'success' ? '✓' : state === 'error' ? '!' : state === 'pending' ? '' : 'i'
}

function request(action, payload) {
  if (!port || !revision) {
    setStatus('Open this app through O Chat before using Agent actions.', 'error')
    return Promise.reject(new Error('Control Center is not connected'))
  }
  const id = `default-control-center:${Date.now()}:${++sequence}`
  port.postMessage({
    type: 'connectonion.control-center/request',
    version: BRIDGE_VERSION,
    revision,
    id,
    action,
    payload,
  })
  setStatus(action === 'run_skill' ? 'Starting skill in Chat…' : 'Sending message to Chat…', 'pending')
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

function icon(pathData) {
  const svg = document.createElementNS(SVG_NS, 'svg')
  svg.setAttribute('viewBox', '0 0 24 24')
  svg.setAttribute('fill', 'none')
  svg.setAttribute('stroke', 'currentColor')
  svg.setAttribute('stroke-width', '2')
  const path = document.createElementNS(SVG_NS, 'path')
  path.setAttribute('d', pathData)
  svg.append(path)
  return svg
}

function skillArrow() {
  const wrap = document.createElement('span')
  wrap.className = 'skill-arrow'
  wrap.setAttribute('aria-hidden', 'true')
  wrap.append(icon('M5 12h14M13 6l6 6-6 6'))
  return wrap
}

function emptyState(title, description) {
  const empty = document.createElement('div')
  empty.className = 'empty-state'
  const emptyIcon = document.createElement('span')
  emptyIcon.className = 'empty-icon'
  emptyIcon.setAttribute('aria-hidden', 'true')
  emptyIcon.append(icon('m13 2-2 7h7l-7 13 2-8H6l7-12Z'))
  const copy = document.createElement('span')
  const heading = document.createElement('strong')
  heading.textContent = title
  const detail = document.createElement('span')
  detail.textContent = description
  copy.append(heading, detail)
  empty.append(emptyIcon, copy)
  return empty
}

function renderSkills(skills = []) {
  skillList.replaceChildren()
  skillCount.textContent = skills.length === 1 ? '1 available' : `${skills.length} available`
  if (!skills.length) {
    skillList.append(emptyState(
      'No published skills yet',
      'You can still send this Agent a message above.',
    ))
    return
  }
  for (const skill of skills) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'skill-button'
    button.setAttribute('aria-label', `Run ${skill.name}`)

    const copy = document.createElement('span')
    const name = document.createElement('span')
    name.className = 'skill-name'
    name.textContent = skill.name
    const description = document.createElement('span')
    description.className = 'skill-description'
    description.textContent = skill.description || 'Run this skill in the current Chat.'
    copy.append(name, description)
    button.append(copy, skillArrow())

    button.addEventListener('click', () => {
      button.disabled = true
      void request('run_skill', { skill: skill.name })
        .catch(() => {})
        .finally(() => { button.disabled = false })
    })
    skillList.append(button)
  }
}

function receive(message = {}) {
  if (message.version !== BRIDGE_VERSION || message.revision !== revision) return
  if (message.type === 'connectonion.control-center/context') {
    document.querySelector('#agent-name').textContent = message.agent?.name || 'Your Agent'
    renderSkills(message.skills)
    const hasChat = Boolean(message.conversation?.sessionId)
    connectionLabel.textContent = hasChat ? 'Current Chat' : 'Ready'
    conversationLabel.textContent = hasChat ? 'Current Chat' : 'Creates a Chat on send'
    connection.classList.add('connected')
    submit.disabled = false
    setStatus(hasChat
      ? 'Messages and skills continue in the current Chat.'
      : 'Your first action will create a new Chat.', 'success')
    return
  }
  if (message.type !== 'connectonion.control-center/response') return
  const waiter = pending.get(message.id)
  if (!waiter) return
  pending.delete(message.id)
  if (message.ok) {
    setStatus('Sent. Continue in Chat to see the Agent reply.', 'success')
    waiter.resolve(message.result)
  } else {
    const error = new Error(message.error?.message || 'The Agent action was rejected.')
    setStatus(error.message, 'error')
    waiter.reject(error)
  }
}

addEventListener('message', event => {
  const message = event.data || {}
  if (message.type !== 'connectonion.control-center/connect') return
  if (message.version !== BRIDGE_VERSION || !event.ports[0]) return
  port?.close()
  revision = message.revision
  port = event.ports[0]
  port.onmessage = event => receive(event.data)
  port.onmessageerror = () => setStatus('O Chat could not read the Agent response.', 'error')
  port.start()
})

form.addEventListener('submit', event => {
  event.preventDefault()
  const message = input.value.trim()
  if (!message) return
  submit.disabled = true
  void request('send_message', { message })
    .then(() => {
      input.value = ''
      input.style.height = ''
    })
    .catch(() => {})
    .finally(() => { submit.disabled = false })
})

input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    form.requestSubmit()
  }
})

input.addEventListener('input', () => {
  input.style.height = 'auto'
  input.style.height = `${Math.min(input.scrollHeight, 320)}px`
})
