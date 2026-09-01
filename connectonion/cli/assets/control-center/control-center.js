const BRIDGE_VERSION = 1
let port = null
let revision = null
let sequence = 0
const pending = new Map()

const connection = document.querySelector('#connection')
const connectionLabel = document.querySelector('#connection-label')
const status = document.querySelector('#status')
const form = document.querySelector('#message-form')
const input = document.querySelector('#message')
const submit = form.querySelector('button[type="submit"]')
const overview = document.querySelector('#overview')
const quickCard = document.querySelector('#quick-card')
const quickActions = document.querySelector('#quick-actions')
const capabilityList = document.querySelector('#capability-list')
const capabilityCount = document.querySelector('#capability-count')
const skillFilter = document.querySelector('#skill-filter')
const searchEmpty = document.querySelector('#search-empty')
const agentAddress = document.querySelector('#agent-address')
const diagnosticSkills = document.querySelector('#diagnostic-skills')
const diagnosticConversation = document.querySelector('#diagnostic-conversation')
const appRevision = document.querySelector('#app-revision')

function setStatus(message, state = 'idle') {
  status.dataset.state = state
  status.textContent = message
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
  setStatus(action === 'run_skill' ? 'Starting skill in Chat…' : 'Sending to Chat…', 'pending')
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

function firstSentence(value = '') {
  const text = String(value).replace(/\s+/g, ' ').trim()
  return text.split(/(?<=[.!?])\s/, 1)[0]
}

function skillButton(skill) {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'skill'
  button.dataset.skill = skill.name
  button.setAttribute('aria-label', `Run ${skill.name}`)

  const name = document.createElement('span')
  name.className = 'name'
  name.textContent = skill.name
  const description = document.createElement('span')
  description.className = 'desc'
  description.textContent = firstSentence(skill.description)
  button.append(name, description)

  button.addEventListener('click', () => {
    button.disabled = true
    void request('run_skill', { skill: skill.name })
      .catch(() => {})
      .finally(() => { button.disabled = false })
  })
  return button
}

function emptyCapabilities() {
  const empty = document.createElement('section')
  empty.className = 'empty'
  const copy = document.createElement('p')
  copy.append('No published skills yet. Add one to ')
  const path = document.createElement('code')
  path.textContent = '.co/skills/'
  copy.append(path, ' and it appears here.')
  empty.append(copy)
  return empty
}

function renderSkills(skills = []) {
  const ordered = [...skills].sort((left, right) => left.name.localeCompare(right.name))
  quickActions.replaceChildren(...ordered.slice(0, 3).map(skillButton))
  quickCard.hidden = ordered.length === 0
  overview.classList.toggle('single', ordered.length === 0)

  capabilityList.replaceChildren()
  if (ordered.length) {
    capabilityList.append(...ordered.map(skillButton))
  } else {
    capabilityList.append(emptyCapabilities())
  }

  capabilityCount.textContent = ordered.length
    ? `${ordered.length} skill${ordered.length === 1 ? '' : 's'}`
    : 'None published'
  diagnosticSkills.textContent = ordered.length
    ? `${ordered.length} published skill${ordered.length === 1 ? '' : 's'}`
    : 'None published'
  skillFilter.hidden = ordered.length <= 6
  skillFilter.value = ''
  searchEmpty.hidden = true
}

function filterSkills() {
  const query = skillFilter.value.trim().toLocaleLowerCase()
  let visible = 0
  for (const button of capabilityList.querySelectorAll('.skill')) {
    const matches = !query || button.textContent.toLocaleLowerCase().includes(query)
    button.hidden = !matches
    if (matches) visible += 1
  }
  searchEmpty.hidden = visible !== 0
}

function receive(message = {}) {
  if (message.version !== BRIDGE_VERSION || message.revision !== revision) return
  if (message.type === 'connectonion.control-center/context') {
    const name = message.agent?.name || 'Connect AI'
    document.querySelector('#agent-name').textContent = name
    document.querySelector('#agent-initial').textContent = name.trim()[0] || 'C'
    document.title = `${name} · Control Center`
    renderSkills(message.skills)
    const hasChat = Boolean(message.conversation?.sessionId)
    agentAddress.textContent = message.agent?.address || 'Unavailable'
    diagnosticConversation.textContent = hasChat ? 'Current Chat' : 'Created by the first action'
    appRevision.textContent = message.revision
    connectionLabel.textContent = hasChat ? 'Current Chat' : 'First action creates a Chat'
    connection.classList.add('connected')
    submit.disabled = false
    setStatus(hasChat ? 'Actions continue in Chat.' : 'Ready for the first action.', 'success')
    return
  }
  if (message.type !== 'connectonion.control-center/response') return
  const waiter = pending.get(message.id)
  if (!waiter) return
  pending.delete(message.id)
  if (message.ok) {
    setStatus('Sent. The reply appears in Chat.', 'success')
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
  input.style.height = `${Math.min(input.scrollHeight, 240)}px`
})

skillFilter.addEventListener('input', filterSkills)
