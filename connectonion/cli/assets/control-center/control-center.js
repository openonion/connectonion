const BRIDGE_VERSION = 1
let port = null
let revision = null
let sequence = 0
const pending = new Map()

const connection = document.querySelector('#connection')
const status = document.querySelector('#status')
const form = document.querySelector('#message-form')
const input = document.querySelector('#message')
const submit = form.querySelector('button[type="submit"]')
const skillList = document.querySelector('#skills')

function setStatus(message) {
  status.textContent = message
}

function request(action, payload) {
  if (!port || !revision) {
    setStatus('Open this app through O Chat before using Agent actions.')
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
  setStatus('Sent to Agent. The reply will appear in Chat.')
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

function renderSkills(skills = []) {
  skillList.replaceChildren()
  if (!skills.length) {
    const empty = document.createElement('span')
    empty.className = 'muted'
    empty.textContent = 'This Agent publishes no project skills yet.'
    skillList.append(empty)
    return
  }
  for (const skill of skills) {
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = skill.description ? `${skill.name} — ${skill.description}` : skill.name
    button.addEventListener('click', () => {
      void request('run_skill', { skill: skill.name }).catch(() => {})
    })
    skillList.append(button)
  }
}

function receive(message = {}) {
  if (message.version !== BRIDGE_VERSION || message.revision !== revision) return
  if (message.type === 'connectonion.control-center/context') {
    document.querySelector('#agent-name').textContent = message.agent?.name || 'Your Agent'
    renderSkills(message.skills)
    connection.textContent = message.conversation?.sessionId ? 'Current Chat' : 'Ready to create Chat'
    connection.classList.add('connected')
    submit.disabled = false
    setStatus(message.conversation?.sessionId
      ? 'Actions continue in the current Chat.'
      : 'The first action will create a Chat.')
    return
  }
  if (message.type !== 'connectonion.control-center/response') return
  const waiter = pending.get(message.id)
  if (!waiter) return
  pending.delete(message.id)
  if (message.ok) {
    setStatus('Sent to Agent. Continue in Chat to see the reply.')
    waiter.resolve(message.result)
  } else {
    const error = new Error(message.error?.message || 'The Agent action was rejected.')
    setStatus(error.message)
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
  port.start()
})

form.addEventListener('submit', event => {
  event.preventDefault()
  const message = input.value.trim()
  if (!message) return
  input.value = ''
  void request('send_message', { message }).catch(() => {})
})
