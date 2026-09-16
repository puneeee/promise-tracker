import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const API = import.meta.env.VITE_API_URL ?? '/api'
const browserFetch = window.fetch.bind(window)
window.fetch = (async (input, init) => {
  const response = await browserFetch(input, { ...init, credentials: 'include' })
  if (response.status === 401 && !window.location.pathname.includes('/auth/')) window.location.assign(`${API}/auth/google/login`)
  return response
}) as typeof fetch

type PromiseItem = { id: string; title: string; category: string; tracking_mode: string; unit: string | null; target_value: number | null; frequency: string; is_locked: boolean; current_progress: number; completion_percent: number }
type Group = { id: string; space_id: string; name: string; role: string }
type CurrentUser = { id: string; email: string; display_name: string; personal_space_id: string }
const modes: Record<string, string> = { check_off: 'Check off', quantity: 'Quantity', duration: 'Duration', cumulative: 'Cumulative goal', percentage: 'Percentage', custom: 'Custom quantity' }

export default function App() {
  const [items, setItems] = useState<PromiseItem[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [space, setSpace] = useState('')
  const [show, setShow] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const group = groups.find(g => g.space_id === space)
  const personalSpaceId = user?.personal_space_id ?? ''

  const loadAccount = async () => {
    try {
      const [meResponse, groupsResponse] = await Promise.all([fetch(`${API}/me`), fetch(`${API}/groups`)])
      if (!meResponse.ok) throw Error('Could not load your account.')
      const account = await meResponse.json() as CurrentUser
      setUser(account)
      setSpace(current => current || account.personal_space_id)
      if (groupsResponse.ok) setGroups(await groupsResponse.json())
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not reach the API.') }
  }
  const loadPromises = async () => {
    if (!space) return
    setLoading(true)
    try {
      const response = await fetch(`${API}/spaces/${space}/promises`)
      if (!response.ok) throw Error('Could not load promises.')
      setItems(await response.json()); setError('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not reach the API.') } finally { setLoading(false) }
  }
  useEffect(() => { void loadAccount() }, [])
  useEffect(() => { void loadPromises() }, [space])

  const summary = useMemo(() => ({ done: items.filter(x => x.completion_percent >= 100).length, avg: items.length ? Math.round(items.reduce((total, item) => total + item.completion_percent, 0) / items.length) : 0 }), [items])
  const add = async (item: PromiseItem) => {
    const value = item.tracking_mode === 'check_off' ? 1 : Number(prompt(`Add ${item.unit ?? 'progress'} to “${item.title}”`, '1'))
    if (!value || value <= 0) return
    const response = await fetch(`${API}/promises/${item.id}/progress`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ value }) })
    if (!response.ok) { setError('Could not save progress.'); return }
    void loadPromises()
  }
  const newGroup = async () => {
    const name = prompt('Name your accountability group')?.trim()
    if (!name) return
    const response = await fetch(`${API}/groups`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, join_policy: 'invite_link', timezone: 'Asia/Kolkata' }) })
    if (!response.ok) { setError('Could not create group.'); return }
    const next = await response.json() as Group
    setGroups(current => [...current, next]); setSpace(next.space_id)
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

  return <main className="app"><aside><div className="brand"><i>✓</i> promise</div><small>YOUR SPACES</small><button className={space === personalSpaceId ? 'active' : ''} onClick={() => setSpace(personalSpaceId)}>◒ My promises</button><small>GROUPS</small>{groups.map(item => <button key={item.id} className={space === item.space_id ? 'active' : ''} onClick={() => setSpace(item.space_id)}>◉ {item.name}</button>)}<button className="new-group" onClick={newGroup}>＋ Create a group</button><footer className="profile"><button className="profile-trigger" onClick={() => setProfileOpen(open => !open)} aria-expanded={profileOpen}><b>{initials}</b><span><strong>{user?.display_name ?? 'Loading…'}</strong>{user?.email ?? ''}</span></button>{profileOpen && <div className="profile-menu"><strong>{user?.display_name}</strong><small>{user?.email}</small><button onClick={logout}>Log out</button></div>}</footer></aside><section className="work"><header><div><small>{group ? 'ACCOUNTABILITY GROUP' : 'PERSONAL SPACE'}</small><h1>{group?.name ?? 'My promises'}</h1></div><button className="primary" onClick={() => setShow(true)} disabled={!space}>＋ New promise</button></header>{group && <div className="notice">◉ Everything in this group is visible to all members. <button onClick={invite}>Invite people</button></div>}{error && <div className="error">{error}<button onClick={() => setError('')}>×</button></div>}<section className="hero"><div><small>YOUR PROMISES</small><h2>Keep the promises you make to yourself.</h2><p>{items.length ? `You have ${items.length} promises to show up for.` : 'Start with one promise you want to keep.'}</p></div><div className="score"><div style={{ '--p': `${summary.avg * 3.6}deg` } as React.CSSProperties}>{summary.avg}%</div><p><b>Current progress</b>{summary.done} of {items.length} complete</p></div></section><div className="heading"><div><h2>Active promises</h2><p>Small actions, kept consistently.</p></div></div>{loading ? <div className="empty">Loading…</div> : items.length ? <div className="grid">{items.map(item => <Card key={item.id} item={item} add={() => add(item)} />)}</div> : <div className="empty"><em>✦</em><h3>Your first promise starts here.</h3><p>Make it small, specific, and meaningful.</p><button className="primary" onClick={() => setShow(true)} disabled={!space}>Create a promise</button></div>}</section>{show && <PromiseForm space={space} close={() => setShow(false)} done={() => { setShow(false); void loadPromises() }} />}</main>
}

function Card({ item, add }: { item: PromiseItem; add: () => void }) { const total = item.target_value ? `${item.current_progress} / ${item.target_value} ${item.unit ?? ''}` : item.completion_percent ? 'Completed today' : 'Not completed yet'; return <article className={item.completion_percent >= 100 ? 'complete' : ''}><div className="card-head"><b>{item.category[0]}</b><small>{item.frequency}</small><span>•••</span></div><h3>{item.title}</h3><p>{modes[item.tracking_mode]} · {total}</p><div className="track"><i style={{ width: `${item.completion_percent}%` }} /></div><footer><small>{item.completion_percent}% complete</small><button disabled={item.is_locked || item.completion_percent >= 100} onClick={add}>{item.is_locked ? 'Locked' : item.tracking_mode === 'check_off' ? 'Mark done' : 'Log progress'}</button></footer></article> }

function PromiseForm({ space, close, done }: { space: string; close: () => void; done: () => void }) { const [mode, setMode] = useState('check_off'), [schedule, setSchedule] = useState('recurring'), [title, setTitle] = useState(''), [start, setStart] = useState(''), [end, setEnd] = useState(''), [error, setError] = useState(''), [saving, setSaving] = useState(false); const valid = title.trim().length >= 5; const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); if (!valid) { setError('Add a title with at least 5 characters.'); return } if (schedule === 'date_range' && (!start || !end || end < start)) { setError('Choose a valid start and end date.'); return } setSaving(true); setError(''); try { const numeric = mode !== 'check_off'; const body = { title: title.trim(), category: form.get('category'), tracking_mode: mode, unit: numeric ? form.get('unit') : null, target_value: numeric ? Number(form.get('target')) : null, schedule_type: schedule, frequency: schedule === 'date_range' ? 'date_range' : form.get('frequency'), start_date: schedule === 'date_range' ? start : null, end_date: schedule === 'date_range' ? end : null, why_it_matters: form.get('why') || null }; const response = await fetch(`${API}/spaces/${space}/promises`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); if (!response.ok) { const value = await response.json(); const detail = Array.isArray(value.detail) ? value.detail.map((entry: { msg: string }) => entry.msg).join(', ') : value.detail; throw Error(detail || `Request failed (${response.status})`) } done() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not create promise.') } finally { setSaving(false) } }; return <div className="modal"><form noValidate onSubmit={submit}><button className="close" type="button" onClick={close}>×</button><small>NEW PROMISE</small><h2>What will you show up for?</h2>{error && <p className="form-error">{error}</p>}<label>Promise title<input value={title} onChange={event => setTitle(event.target.value)} placeholder="e.g. Drink water every day" autoFocus /></label><div className="row"><label>Category<select name="category"><option>Health</option><option>Fitness</option><option>Learning</option><option>Career</option><option>Personal</option></select></label><label>Track it by<select value={mode} onChange={event => setMode(event.target.value)}>{Object.entries(modes).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label></div>{mode !== 'check_off' && <div className="row"><label>Target<input name="target" type="number" min="0.01" step="0.01" defaultValue="1" required /></label><label>Unit<input name="unit" placeholder="litres, km, hours" required /></label></div>}<div className="row"><label>Promise type<select value={schedule} onChange={event => { setSchedule(event.target.value); setStart(''); setEnd('') }}><option value="recurring">Recurring</option><option value="date_range">Date range</option></select></label><label>Repeat<select name="frequency" disabled={schedule === 'date_range'}><option>daily</option><option>weekly</option><option>monthly</option></select></label></div>{schedule === 'date_range' && <div className="row"><label>Start date<input type="date" value={start} onChange={event => { setStart(event.target.value); if (end && end < event.target.value) setEnd('') }} required /></label><label>End date<input type="date" value={end} onChange={event => setEnd(event.target.value)} min={start || undefined} disabled={!start} required /></label></div>}<label>Why does this matter? <span>(optional)</span><textarea name="why" rows={3} /></label><div className="actions"><button type="button" onClick={close}>Cancel</button><button className="primary" disabled={!valid || saving}>{saving ? 'Creating…' : 'Create promise'}</button></div></form></div> }
