import {connectControlCenter} from './sdk.js'
const suggestions = await fetch('./suggestions.json').then(response => response.json())
let client = null
let snapshot = null
let pending = false
let lastTask = ''
const $ = selector => document.querySelector(selector)
const form = $('#message-form')
const input = $('#message')
const submit = form.querySelector('[type="submit"]')
const status = $('#status')
const capabilityList = $('#capability-list')
const pins = $('#pinned-skills')

function setStatus(message, state = 'idle') {
  status.dataset.state = state
  status.textContent = message
}

function updateActions() {
  const ready = snapshot?.connectionState === 'connected' && snapshot.status === 'idle' && !pending
  for (const button of document.querySelectorAll('.run, .skill')) button.disabled = !ready
  // The one motion moment: while a run is in flight the ask folds into a Running row.
  const running = pending || snapshot?.status === 'working'
  if (running) form.dataset.ochatState = 'running'
  else delete form.dataset.ochatState
  $('#running-what').textContent = lastTask || 'A task started in Chat'
}

function request(skill, message, clearDraft = false) {
  const draft = input.value
  pending = true
  lastTask = skill ? skillTitle(snapshot.skills.find(s => s.name === skill) || {name: skill}) : message
  updateActions()
  setStatus('Running in Chat', 'pending')
  const action = skill ? client.runSkill(skill) : client.sendMessage(message)
  return action.then(() => {
    pending = false
    if (clearDraft && input.value === draft) input.value = ''
    setStatus('✓ Done', 'success')
    updateActions()
  }, error => {
    pending = false
    setStatus('✕ Failed: ' + error.message, 'error')
    updateActions()
  })
}

// SKILL.md's title, else the slug in sentence case: post-to-x reads "Post to X".
function skillTitle(skill) {
  const title = String(skill.title || '').trim()
  if (title) return title
  const text = String(skill.name).split(/[-_\s]+/).filter(Boolean).map(w => w.length === 1 ? w.toUpperCase() : w).join(' ')
  return text.slice(0, 1).toUpperCase() + text.slice(1)
}

function span(className, text) {
  const element = document.createElement('span')
  element.className = className
  element.textContent = text
  return element
}

// All skills rows also show /slug: what you type, and what the search should find.
function skillButton(skill, action = () => request(skill.name), withSlug = false) {
  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'skill'
  const name = span('name', skillTitle(skill))
  const description = document.createElement('span')
  description.className = 'desc'
  description.textContent = String(skill.description || '').replace(/\s+/g, ' ').split(/(?<=[.!?])\s/, 1)[0]
  if (withSlug) {
    const row = span('title-row', '')
    row.append(name, span('slug', '/' + skill.name))
    button.append(row, description)
  } else button.append(name, description)
  button.addEventListener('click', action)
  return button
}

function renderSuggestions() {
  // Suggestions are prompts, never invented published skill names.
  pins.replaceChildren(...suggestions.map(item => skillButton(item, () => request(null, item.prompt))))
}

function renderSkills(skills = []) {
  const ordered = [...skills].sort((a, b) => a.name.localeCompare(b.name))
  capabilityList.replaceChildren(...ordered.map(skill => skillButton(skill, undefined, true)))
  $('#all-skills').hidden = !ordered.length
  $('#no-skills').hidden = ordered.length > 0
  $('#quick-title').textContent = ordered.length ? 'Pinned skills' : 'Suggested'
  if (ordered.length) pins.replaceChildren(...ordered.slice(0, 4).map(skill => skillButton(skill)))
  else renderSuggestions()
  $('#capability-count').textContent = ordered.length
  $('#diagnostic-skills').textContent = ordered.length
  $('#skill-filter').value = ''
  $('#search-empty').hidden = true
  updateActions()
}

function filterSkills() {
  const query = $('#skill-filter').value.trim().toLocaleLowerCase()
  let visible = 0
  for (const button of capabilityList.querySelectorAll('.skill')) {
    button.hidden = !button.textContent.toLocaleLowerCase().includes(query)
    if (!button.hidden) visible += 1
  }
  $('#search-empty').hidden = visible > 0 || !snapshot?.skills.length
}

function renderIdentity(value) {
  const name = value.agentName || 'Agent'
  $('#agent-initial').textContent = name.slice(0, 1)
  $('#run-label').textContent = `What should ${name} do?`
  document.title = `${name} · Control Center`
  const address = value.agentAddress
  $('#agent-address').textContent = address || 'Available after connection'
  $('#card-address').textContent = address ? address.slice(0, 6) + '…' + address.slice(-4) : 'Not connected'
  $('#copy-address').disabled = !address
  const state = value.connectionState
  $('#connection-label').textContent = state === 'connected' ? 'Online' : state === 'reconnecting' ? 'Connecting…' : 'Offline'
  $('#connection').className = 'presence ' + (state === 'connected' ? '' : state === 'reconnecting' ? 'connecting' : 'offline')
}

function renderRecent(value) {
  const items = value.chatItems.slice(-12).map(item => {
    const row = document.createElement('p')
    const who = document.createElement('b')
    who.textContent = item.type === 'user' ? 'You' : item.type === 'tool_call' ? item.name : value.agentName || 'Agent'
    row.append(who, ' ' + String(item.content || item.text || item.summary || item.type).slice(0, 2000))
    return row
  })
  $('#recent-chat').replaceChildren(...items)
  $('#history-note').textContent = value.truncated ? 'Recent conversation; older items were omitted.' : items.length ? 'Recent conversation' : 'No recent runs yet.'
}

let previousSkills = ''
function renderSnapshot(value) {
  snapshot = value
  renderIdentity(value)
  const serialized = JSON.stringify(value.skills)
  if (previousSkills !== serialized) { renderSkills(value.skills); previousSkills = serialized }
  $('#diagnostic-conversation').textContent = value.sessionId || 'Created by the first action'
  renderRecent(value)
  updateActions()
  if (value.status !== 'working' && !pending) lastTask = ''
  if (!pending && status.dataset.state !== 'success') setStatus(value.connectionState !== 'connected' ? 'Open through O Chat to run tasks' : value.status === 'waiting' ? 'Waiting for your answer in Chat' : 'Opens in Chat so you can follow it')
}

renderSkills()
const parameters = new URLSearchParams(location.hash.slice(1))
$('#app-revision').textContent = parameters.get('co-revision') || 'Local preview'
function connect() {
  $('#retry-connection').hidden = true
  $('#connection-label').textContent = 'Connecting…'
  $('#connection').className = 'presence connecting'
  connectControlCenter({parentOrigin: parameters.get('co-parent'), revision: parameters.get('co-revision')})
    .then(connection => { client = connection; client.subscribe(renderSnapshot) }, error => {
      $('#connection-label').textContent = "Can't connect"
      $('#connection').className = 'presence failed'
      $('#retry-connection').hidden = false
      setStatus(error.message, 'error')
    })
}

if (parameters.get('co-parent') && parameters.get('co-revision')) connect()
$('#retry-connection').addEventListener('click', connect)

form.addEventListener('submit', event => {
  event.preventDefault()
  const message = input.value.trim()
  if (submit.disabled || !message) return
  request(null, message, true)
})
input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    form.requestSubmit()
  }
})
$('#skill-filter').addEventListener('input', filterSkills)
$('#copy-address').addEventListener('click', () => {
  navigator.clipboard.writeText(snapshot.agentAddress).then(() => {
    $('#copy-address').textContent = 'Copied'
    setTimeout(() => { $('#copy-address').textContent = 'Copy' }, 2000)
  }, error => setStatus('Could not copy address: ' + error.message, 'error'))
})
input.addEventListener('input', () => {
  if (status.dataset.state === 'success') setStatus('Opens in Chat so you can follow it')
})
// Asks O Chat to show the Chat tab, where the run is. Without a parent there is no Chat to open.
$('#open-chat').hidden = !parameters.get('co-parent')
$('#open-chat').addEventListener('click', () => {
  window.parent.postMessage({type: 'connectonion.control-center/open-chat'}, parameters.get('co-parent'))
})
