import {connectControlCenter} from './sdk.js'
let client = null

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

async function request(action, payload) {
  if (!client) throw new Error('Open this app through O Chat before using Agent actions.')
  setStatus(action === 'run_skill' ? 'Running skill in Chat…' : 'Waiting for the Agent…', 'pending')
  try {
    const result = action === 'run_skill'
      ? await client.runSkill(payload.skill, payload.args)
      : await client.sendMessage(payload.message)
    setStatus('The reply appears in Chat.', 'success')
    return result
  } catch (error) {
    setStatus(error.message, 'error')
    throw error
  }
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

let previousSkills = ''
function renderSnapshot(snapshot) {
  const serialized = JSON.stringify(snapshot.skills)
  if (previousSkills !== serialized) { renderSkills(snapshot.skills); previousSkills = serialized }
  const ready = snapshot.connectionState === 'connected'
  agentAddress.textContent = snapshot.agentAddress
  diagnosticConversation.textContent = snapshot.sessionId || 'Created by the first action'
  connectionLabel.textContent = ready ? (snapshot.status === 'idle' ? 'Connected' : 'Agent ' + snapshot.status) : snapshot.connectionState
  connection.classList.toggle('connected', ready)
  submit.disabled = !ready || snapshot.status !== 'idle'
  const transcript = document.querySelector('#recent-chat')
  const items = snapshot.chatItems.slice(-12).map(item => {
    const row = document.createElement('p')
    const who = item.type === 'user' ? 'You' : item.type === 'tool_call' ? item.name : 'Agent'
    const content = item.content || item.text || item.summary || item.status || item.type
    row.textContent = who + ': ' + String(content).slice(0,2000)
    return row
  })
  transcript.replaceChildren(...items)
  document.querySelector('#history-note').textContent = snapshot.truncated ? 'Recent conversation; older items were omitted.' : 'Live conversation from O Chat.'
}

const parameters = new URLSearchParams(location.hash.slice(1))
appRevision.textContent = parameters.get('co-revision') || 'Local preview'
if (parameters.get('co-parent') && parameters.get('co-revision')) {
  connectControlCenter({parentOrigin:parameters.get('co-parent'), revision:parameters.get('co-revision')})
    .then(connection => { client=connection; client.subscribe(renderSnapshot); setStatus('Connected to Chat.','success') })
    .catch(error => setStatus(error.message,'error'))
} else {
  setStatus('Preview only. Open this app through an approved O Chat session for Agent actions.')
}

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
