import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const API = import.meta.env.VITE_API_URL ?? '/api'
const browserFetch = window.fetch.bind(window)
window.fetch = (async (input, init) => {
  const response = await browserFetch(input, { ...init, credentials: 'include' })
  if (response.status === 401 && !window.location.pathname.includes('/auth/')) {
    window.location.assign(`${API}/auth/google/login?next=${encodeURIComponent(window.location.href)}`)
  }
  return response
}) as typeof fetch

type PromiseItem = { id: string; title: string; category: string; tracking_mode: string; unit: string | null; target_value: number | null; frequency: string; is_locked: boolean; current_progress: number; completion_percent: number }
type Group = { id: string; space_id: string; name: string; role: string; join_policy?: string }
type CurrentUser = { id: string; email: string; display_name: string; personal_space_id: string }
const modes: Record<string, string> = { check_off: 'Check off', quantity: 'Quantity', duration: 'Duration', cumulative: 'Cumulative goal', percentage: 'Percentage', custom: 'Custom quantity' }

export default function App() {
  const [items, setItems] = useState<PromiseItem[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [space, setSpace] = useState('')
  const [showPromise, setShowPromise] = useState(false)
  const [showGroup, setShowGroup] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const group = groups.find(item => item.space_id === space)
  const personalSpaceId = user?.personal_space_id ?? ''

  const loadPromises = async () => {
    if (!space) return
    setLoading(true)
    try {
      const response = await fetch(`${API}/spaces/${space}/promises`)
      if (!response.ok) throw Error('Could not load promises.')
      setItems(await response.json()); setError('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not reach the API.') } finally { setLoading(false) }
  }

  const loadAccount = async () => {
    try {
      const [meResponse, groupsResponse] = await Promise.all([fetch(`${API}/me`), fetch(`${API}/groups`)])
      if (!meResponse.ok) throw Error('Could not load your account.')
      const account = await meResponse.json() as CurrentUser
      const initialGroups: Group[] = groupsResponse.ok ? await groupsResponse.json() : []
      setUser(account)
      setGroups(initialGroups)
      setSpace(account.personal_space_id)
      const token = new URLSearchParams(window.location.search).get('invite')
      if (token) {
        const joinResponse = await fetch(`${API}/invites/${encodeURIComponent(token)}/join`, { method: 'POST' })
        history.replaceState({}, '', window.location.pathname)
        if (!joinResponse.ok) {
          const body = await joinResponse.json().catch(() => ({}))
          throw Error(body.detail || 'Could not join this group.')
        }
        const joined = await joinResponse.json() as Group
        setGroups(current => current.some(item => item.id === joined.id) ? current : [...current, joined])
        setSpace(joined.space_id)
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not reach the API.') }
  }

  useEffect(() => { void loadAccount() }, [])
  useEffect(() => { void loadPromises() }, [space])
  const summary = useMemo(() => ({ done: items.filter(item => item.completion_percent >= 100).length, avg: items.length ? Math.round(items.reduce((total, item) => total + item.completion_percent, 0) / items.length) : 0 }), [items])

  const addProgress = async (item: PromiseItem) => {
    const value = item.tracking_mode === 'check_off' ? 1 : Number(prompt(`Add ${item.unit ?? 'progress'} to “${item.title}”`, '1'))
    if (!value || value <= 0) return
    const response = await fetch(`${API}/promises/${item.id}/progress`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ value }) })
    if (!response.ok) { setError('Could not save progress.'); return }
    void loadPromises()
  }
  const archive = async (item: PromiseItem) => {
    if (!confirm(`Archive “${item.title}”? You can keep its history, but it will leave your active list.`)) return
    const response = await fetch(`${API}/promises/${item.id}/archive`, { method: 'POST' })
    if (!response.ok) { setError('Could not archive promise.'); return }
    void loadPromises()
  }
  const duplicate = async (item: PromiseItem) => {
    const response = await fetch(`${API}/promises/${item.id}/duplicate`, { method: 'POST' })
    if (!response.ok) { setError('Could not duplicate promise.'); return }
    void loadPromises()
  }
  const createGroup = async (name: string, joinPolicy: string) => {
    const response = await fetch(`${API}/groups`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, join_policy: joinPolicy, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata' }) })
    if (!response.ok) throw Error('Could not create group.')
    const next = await response.json() as Group
    setGroups(current => [...current, next]); setSpace(next.space_id); setShowGroup(false)
  }
  const invite = async () => {
    if (!group) return
    try {
      const response = await fetch(`${API}/groups/${group.id}/invites`, { method: 'POST' })
      if (!response.ok) throw Error('Could not create an invite link.')
      const inviteData = await response.json()
      const link = `${location.origin}${inviteData.join_path}`
      await navigator.clipboard.writeText(link); alert(`Invite link copied:\n\n${link}`)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not create invite link.') }
  }
  const logout = async () => { await fetch(`${API}/auth/logout`, { method: 'POST' }); window.location.reload() }
  const initials = (user?.display_name || 'U').trim().slice(0, 1).toUpperCase()

  return <main className="app"><aside><div className="brand"><i>✓</i> promise</div><nav className="spaces-nav"><small>YOUR SPACES</small><button className={space === personalSpaceId ? 'active' : ''} onClick={() => setSpace(personalSpaceId)}>◒ My promises</button><small>GROUPS</small>{groups.map(item => <button key={item.id} className={space === item.space_id ? 'active' : ''} onClick={() => setSpace(item.space_id)}>◉ {item.name}</button>)}<button className="new-group" onClick={() => setShowGroup(true)}>＋ Create a group</button></nav><footer className="profile"><button className="profile-trigger" onClick={() => setProfileOpen(open => !open)} aria-expanded={profileOpen}><b>{initials}</b><span><strong>{user?.display_name ?? 'Loading…'}</strong>{user?.email ?? ''}</span></button>{profileOpen && <div className="profile-menu"><strong>{user?.display_name}</strong><small>{user?.email}</small><button onClick={logout}>Log out</button></div>}</footer></aside><section className="work"><header><div><small>{group ? 'ACCOUNTABILITY GROUP' : 'PERSONAL SPACE'}</small><h1>{group?.name ?? 'My promises'}</h1></div><button className="primary" onClick={() => setShowPromise(true)} disabled={!space}>＋ New promise</button></header>{group && <div className="notice">◉ Everything in this group is visible to all members. <button onClick={invite}>Invite people</button></div>}{error && <div className="error">{error}<button onClick={() => setError('')}>×</button></div>}<section className="hero"><div><small>YOUR PROMISES</small><h2>Keep the promises you make to yourself.</h2><p>{items.length ? `You have ${items.length} promises to show up for.` : 'Start with one promise you want to keep.'}</p></div><div className="score"><div style={{ '--p': `${summary.avg * 3.6}deg` } as React.CSSProperties}>{summary.avg}%</div><p><b>Current progress</b>{summary.done} of {items.length} complete</p></div></section><div className="heading"><div><h2>Active promises</h2><p>Small actions, kept consistently.</p></div></div>{loading ? <div className="empty">Loading…</div> : items.length ? <div className="grid">{items.map(item => <Card key={item.id} item={item} add={() => addProgress(item)} archive={() => archive(item)} duplicate={() => duplicate(item)} />)}</div> : <div className="empty"><em>✦</em><h3>Your first promise starts here.</h3><p>Make it small, specific, and meaningful.</p><button className="primary" onClick={() => setShowPromise(true)} disabled={!space}>Create a promise</button></div>}</section>{showPromise && <PromiseForm space={space} close={() => setShowPromise(false)} done={() => { setShowPromise(false); void loadPromises() }} />}{showGroup && <GroupForm close={() => setShowGroup(false)} create={createGroup} />}</main>
}

function Card({ item, add, archive, duplicate }: { item: PromiseItem; add: () => void; archive: () => void; duplicate: () => void }) {
  const [open, setOpen] = useState(false)
  const total = item.target_value ? `${item.current_progress} / ${item.target_value} ${item.unit ?? ''}` : item.completion_percent ? 'Completed today' : 'Not completed yet'
  return <article className={item.completion_percent >= 100 ? 'complete' : ''}><div className="card-head"><b>{item.category[0]}</b><small>{item.frequency}</small><div className="card-actions"><button className="card-menu" aria-label={`Actions for ${item.title}`} onClick={() => setOpen(value => !value)}>•••</button>{open && <div className="card-menu-popover"><button onClick={() => { setOpen(false); duplicate() }}>Duplicate</button><button onClick={() => { setOpen(false); archive() }}>Archive</button></div>}</div></div><h3>{item.title}</h3><p>{modes[item.tracking_mode]} · {total}</p><div className="track"><i style={{ width: `${item.completion_percent}%` }} /></div><footer><small>{item.completion_percent}% complete</small><button disabled={item.is_locked || item.completion_percent >= 100} onClick={add}>{item.is_locked ? 'Locked' : item.tracking_mode === 'check_off' ? 'Mark done' : 'Log progress'}</button></footer></article>
}

function GroupForm({ close, create }: { close: () => void; create: (name: string, joinPolicy: string) => Promise<void> }) {
  const [name, setName] = useState(''), [joinPolicy, setJoinPolicy] = useState('invite_link'), [error, setError] = useState(''), [saving, setSaving] = useState(false)
  const submit = async (event: FormEvent) => { event.preventDefault(); if (name.trim().length < 3) { setError('Use at least 3 characters for the group name.'); return } setSaving(true); try { await create(name.trim(), joinPolicy) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not create group.') } finally { setSaving(false) } }
  return <div className="modal"><form noValidate onSubmit={submit}><button className="close" type="button" onClick={close}>×</button><small>NEW GROUP</small><h2>Create an accountability group</h2>{error && <p className="form-error">{error}</p>}<label>Group name<input value={name} onChange={event => setName(event.target.value)} placeholder="e.g. Q4 running team" autoFocus /></label><label>How people join<select value={joinPolicy} onChange={event => setJoinPolicy(event.target.value)}><option value="invite_link">Anyone with the invite link</option><option value="admin_approval">Admin approval required</option></select></label><p className="form-hint">All group members can see promises and progress. Personal promises stay private.</p><div className="actions"><button type="button" onClick={close}>Cancel</button><button className="primary" disabled={name.trim().length < 3 || saving}>{saving ? 'Creating…' : 'Create group'}</button></div></form></div>
}

function PromiseForm({ space, close, done }: { space: string; close: () => void; done: () => void }) {
  const [mode, setMode] = useState('check_off'), [schedule, setSchedule] = useState('recurring'), [title, setTitle] = useState(''), [unit, setUnit] = useState(''), [start, setStart] = useState(''), [end, setEnd] = useState(''), [error, setError] = useState(''), [saving, setSaving] = useState(false)
  const numeric = mode !== 'check_off', valid = title.trim().length >= 5 && (!numeric || unit.trim().length > 0)
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); if (!valid) { setError(numeric && !unit.trim() ? 'Add a unit for this tracking mode.' : 'Add a title with at least 5 characters.'); return } if (schedule === 'date_range' && (!start || !end || end < start)) { setError('Choose a valid start and end date.'); return } setSaving(true); setError(''); try { const body = { title: title.trim(), category: form.get('category'), tracking_mode: mode, unit: numeric ? unit.trim() : null, target_value: numeric ? Number(form.get('target')) : null, schedule_type: schedule, frequency: schedule === 'date_range' ? 'date_range' : form.get('frequency'), start_date: schedule === 'date_range' ? start : null, end_date: schedule === 'date_range' ? end : null, why_it_matters: form.get('why') || null }; const response = await fetch(`${API}/spaces/${space}/promises`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); if (!response.ok) { const value = await response.json(); const detail = Array.isArray(value.detail) ? value.detail.map((entry: { msg: string }) => entry.msg).join(', ') : value.detail; throw Error(detail || `Request failed (${response.status})`) } done() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not create promise.') } finally { setSaving(false) } }
  return <div className="modal"><form noValidate onSubmit={submit}><button className="close" type="button" onClick={close}>×</button><small>NEW PROMISE</small><h2>What will you show up for?</h2>{error && <p className="form-error">{error}</p>}<label>Promise title<input value={title} onChange={event => setTitle(event.target.value)} placeholder="e.g. Drink water every day" autoFocus /></label><div className="row"><label>Category<select name="category"><option>Health</option><option>Fitness</option><option>Learning</option><option>Career</option><option>Personal</option></select></label><label>Track it by<select value={mode} onChange={event => setMode(event.target.value)}>{Object.entries(modes).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label></div>{numeric && <div className="row"><label>Target<input name="target" type="number" min="0.01" step="0.01" defaultValue="1" required /></label><label>Unit<input value={unit} onChange={event => setUnit(event.target.value)} placeholder="litres, km, hours" required /></label></div>}<div className="row"><label>Promise type<select value={schedule} onChange={event => { setSchedule(event.target.value); setStart(''); setEnd('') }}><option value="recurring">Recurring</option><option value="date_range">Date range</option></select></label><label>Repeat<select name="frequency" disabled={schedule === 'date_range'}><option>daily</option><option>weekly</option><option>monthly</option></select></label></div>{schedule === 'date_range' && <div className="row"><label>Start date<input type="date" value={start} onChange={event => { setStart(event.target.value); if (end && end < event.target.value) setEnd('') }} required /></label><label>End date<input type="date" value={end} onChange={event => setEnd(event.target.value)} min={start || undefined} disabled={!start} required /></label></div>}<label>Why does this matter? <span>(optional)</span><textarea name="why" rows={3} /></label><div className="actions"><button type="button" onClick={close}>Cancel</button><button className="primary" disabled={!valid || saving}>{saving ? 'Creating…' : 'Create promise'}</button></div></form></div>
}
