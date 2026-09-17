import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import "./App.css";

const API = import.meta.env.VITE_API_URL ?? "/api",
  redirectSession = new URLSearchParams(location.hash.slice(1)).get("session");
if (redirectSession) {
  sessionStorage.setItem("promise_session", redirectSession);
  window.history.replaceState({}, "", `${location.pathname}${location.search}`);
}
const rawFetch = window.fetch.bind(window);
window.fetch = (async (input, init) => {
  const headers = new Headers(init?.headers),
    token = sessionStorage.getItem("promise_session");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await rawFetch(input, {
    ...init,
    headers,
    credentials: "include",
  });
  if (response.status === 401)
    window.location.assign(
      `${API}/auth/google/login?next=${encodeURIComponent(location.href)}`,
    );
  return response;
}) as typeof fetch;
type Item = {
  id: string;
  title: string;
  category: string;
  tracking_mode: string;
  unit: string | null;
  target_value: number | null;
  frequency: string;
  schedule_type: string;
  status: string;
  is_locked: boolean;
  current_progress: number;
  completion_percent: number;
  why_it_matters: string | null;
  owner_name: string;
};
type Group = {
  id: string;
  space_id: string;
  name: string;
  role: string;
  join_policy: string;
  timezone: string;
};
type User = { display_name: string; email: string; personal_space_id: string };
type Member = { user_id: string; name: string; email: string; role: string };
type Join = {
  id: string;
  user_id: string;
  name: string;
  email: string;
  created_at: string;
};
type Entry = {
  id: string;
  value: number;
  total: number;
  period_total: number;
  note: string | null;
  completed_at: string;
  in_current_period: boolean;
};
const modes: Record<string, string> = {
  check_off: "Check off",
  quantity: "Quantity",
  duration: "Duration",
  cumulative: "Cumulative goal",
  percentage: "Percentage",
  custom: "Custom quantity",
};
async function detail(response: Response, fallback: string) {
  const body = await response.json().catch(() => ({}));
  return body.detail || fallback;
}

export default function App() {
  const [items, setItems] = useState<Item[]>([]),
    [groups, setGroups] = useState<Group[]>([]),
    [user, setUser] = useState<User | null>(null),
    [space, setSpace] = useState(""),
    [view, setView] = useState("active"),
    [showNew, setShowNew] = useState(false),
    [showGroup, setShowGroup] = useState(false),
    [settings, setSettings] = useState(false),
    [action, setAction] = useState<Item | null>(null),
    [logging, setLogging] = useState<Item | null>(null),
    [historyItem, setHistoryItem] = useState<Item | null>(null),
    [editing, setEditing] = useState<Item | null>(null),
    [profile, setProfile] = useState(false),
    [categoryFilter, setCategoryFilter] = useState("all"),
    [ownerFilter, setOwnerFilter] = useState("all"),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const group = groups.find((g) => g.space_id === space),
    manage = group?.role === "owner" || group?.role === "admin";
  const load = async () => {
    if (!space) return;
    setLoading(true);
    try {
      const r = await fetch(`${API}/spaces/${space}/promises?view=${view}`);
      if (!r.ok) throw Error(await detail(r, "Could not load promises."));
      setItems(await r.json());
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load promises.");
    } finally {
      setLoading(false);
    }
  };
  const loadAccount = async () => {
    try {
      const [me, gl] = await Promise.all([
        fetch(`${API}/me`),
        fetch(`${API}/groups`),
      ]);
      if (!me.ok) throw Error(await detail(me, "Could not load account."));
      if (!gl.ok) throw Error(await detail(gl, "Could not load groups."));
      const account = (await me.json()) as User,
        owned = (await gl.json()) as Group[];
      setUser(account);
      setGroups(owned);
      setSpace(account.personal_space_id);
      const invite = new URLSearchParams(location.search).get("invite");
      if (invite) {
        const join = await fetch(
          `${API}/invites/${encodeURIComponent(invite)}/join`,
          { method: "POST" },
        );
        window.history.replaceState({}, "", location.pathname);
        const body = await join.json();
        if (!join.ok) throw Error(body.detail || "Could not join group.");
        if (body.status === "pending") {
          setError(body.message);
          return;
        }
        setGroups((current) =>
          current.some((g) => g.id === body.id) ? current : [...current, body],
        );
        setSpace(body.space_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load workspace.");
    }
  };
  useEffect(() => {
    void loadAccount();
  }, []);
  useEffect(() => {
    void load();
  }, [space, view]);
  const summary = useMemo(
    () => ({
      done: items.filter((x) => x.completion_percent >= 100).length,
      avg: items.length
        ? Math.round(
            items.reduce((n, x) => n + x.completion_percent, 0) / items.length,
          )
        : 0,
    }),
    [items],
  );
  const categories = useMemo(() => [...new Set(items.map((item) => item.category))].sort(), [items]);
  const owners = useMemo(() => [...new Set(items.map((item) => item.owner_name))].sort(), [items]);
  const visibleItems = items.filter((item) => (categoryFilter === "all" || item.category === categoryFilter) && (ownerFilter === "all" || item.owner_name === ownerFilter));
  const log = async (item: Item, value: number, note: string) => {
    const r = await fetch(`${API}/promises/${item.id}/progress`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value, note: note || null }),
    });
    if (!r.ok) throw Error(await detail(r, "Could not log progress."));
    setLogging(null);
    void load();
  };
  const archive = async (item: Item) => {
    if (!confirm(`Archive “${item.title}”?`)) return;
    const r = await fetch(`${API}/promises/${item.id}/archive`, {
      method: "POST",
    });
    if (!r.ok) setError(await detail(r, "Could not archive promise."));
    else {
      setAction(null);
      void load();
    }
  };
  const duplicate = async (item: Item) => {
    const r = await fetch(`${API}/promises/${item.id}/duplicate`, {
      method: "POST",
    });
    if (!r.ok) setError(await detail(r, "Could not duplicate promise."));
    else {
      setAction(null);
      void load();
    }
  };
  const restore = async (item: Item) => {
    const r = await fetch(`${API}/promises/${item.id}/restore`, { method: "POST" });
    if (!r.ok) setError(await detail(r, "Could not restore promise."));
    else { setAction(null); setView("active"); void load(); }
  };
  const invite = async () => {
    if (!group) return;
    const r = await fetch(`${API}/groups/${group.id}/invites`, {
      method: "POST",
    });
    if (!r.ok) {
      setError(await detail(r, "Could not create invite."));
      return;
    }
    const body = await r.json(),
      link = `${location.origin}${body.join_path}`;
    await navigator.clipboard.writeText(link);
    alert(`Invite link copied:\n\n${link}`);
  };
  const logout = () => {
    sessionStorage.removeItem("promise_session");
    location.assign(
      `${API}/auth/logout?next=${encodeURIComponent(location.href)}`,
    );
  };
  const initials = (user?.display_name || "U")[0].toUpperCase();
  return (
    <main className="app">
      <aside>
        <div className="brand">
          <i>✓</i> promise
        </div>
        <nav className="spaces-nav">
          <small>YOUR SPACES</small>
          <button
            className={space === user?.personal_space_id ? "active" : ""}
            onClick={() => setSpace(user?.personal_space_id ?? "")}
          >
            ◒ My promises
          </button>
          <small>GROUPS</small>
          {groups.map((g) => (
            <button
              key={g.id}
              className={space === g.space_id ? "active" : ""}
              onClick={() => setSpace(g.space_id)}
            >
              ◉ {g.name}
            </button>
          ))}
          <button className="new-group" onClick={() => setShowGroup(true)}>
            ＋ Create a group
          </button>
        </nav>
        <footer className="profile">
          <button className="profile-trigger" onClick={() => setProfile(true)}>
            <b>{initials}</b>
            <span>
              <strong>{user?.display_name ?? "Loading…"}</strong>
              {user?.email ?? ""}
            </span>
          </button>
        </footer>
      </aside>
      <section className="work">
        <header>
          <div>
            <small>{group ? "ACCOUNTABILITY GROUP" : "PERSONAL SPACE"}</small>
            <h1>{group?.name ?? "My promises"}</h1>
          </div>
          <div className="header-actions">
            {group && manage && (
              <button className="secondary" onClick={() => setSettings(true)}>
                Group settings
              </button>
            )}
            <button className="primary" onClick={() => setShowNew(true)}>
              ＋ New promise
            </button>
          </div>
        </header>
        {group && (
          <div className="notice">
            ◉ Everything in this group is visible to all members.{" "}
            <button onClick={invite}>Invite people</button>
          </div>
        )}
        {error && (
          <div className="error">
            {error}
            <button onClick={() => setError("")}>×</button>
          </div>
        )}
        <section className="hero">
          <div>
            <small>
              {view === "active" ? "CURRENT PERIOD" : "PROMISE LIBRARY"}
            </small>
            <h2>
              {view === "active"
                ? "Keep the promises you make to yourself."
                : "Your promise history."}
            </h2>
            <p>
              Recurring progress resets each daily, weekly, or monthly period.
            </p>
          </div>
          <div className="score">
            <div
              style={
                { "--p": `${summary.avg * 3.6}deg` } as React.CSSProperties
              }
            >
              {summary.avg}%
            </div>
            <p>
              <b>Current progress</b>
              {summary.done} of {items.length} complete
            </p>
          </div>
        </section>
          <div className="heading">
          <div>
            <h2>Promises</h2>
            <p>Small actions, kept consistently.</p>
          </div>
            <div className="filters">
              <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} aria-label="Filter by category"><option value="all">All categories</option>{categories.map((category) => <option key={category}>{category}</option>)}</select>
              {group && <select value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)} aria-label="Filter by member"><option value="all">All members</option>{owners.map((owner) => <option key={owner}>{owner}</option>)}</select>}
            </div>
            <div className="tabs">
            {["active", "completed", "archived"].map((tab) => (
              <button
                key={tab}
                className={view === tab ? "selected" : ""}
                onClick={() => setView(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>
        {loading ? (
          <div className="empty">Loading…</div>
          ) : visibleItems.length ? (
            <div className="grid">
              {visibleItems.map((item) => (
              <Card
                key={item.id}
                item={item}
                manage={() => setAction(item)}
                log={() => setLogging(item)}
              />
            ))}
          </div>
        ) : (
          <div className="empty">
            <em>✦</em>
            <h3>No {view} promises</h3>
            <p>
              {view === "active"
                ? "Create a promise to begin tracking."
                : "Your completed and archived promises stay here with their history."}
            </p>
            {view === "active" && (
              <button className="primary" onClick={() => setShowNew(true)}>
                Create a promise
              </button>
            )}
          </div>
        )}
      </section>
      {showNew && (
        <PromiseForm
          space={space}
          close={() => setShowNew(false)}
          done={() => {
            setShowNew(false);
            void load();
          }}
        />
      )}
      {showGroup && (
        <GroupForm
          close={() => setShowGroup(false)}
          done={async (name, policy) => {
            const r = await fetch(`${API}/groups`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                name,
                join_policy: policy,
                timezone:
                  Intl.DateTimeFormat().resolvedOptions().timeZone ||
                  "Asia/Kolkata",
              }),
            });
            if (!r.ok) throw Error(await detail(r, "Could not create group."));
            const next = (await r.json()) as Group;
            setGroups((x) => [...x, next]);
            setSpace(next.space_id);
            setShowGroup(false);
          }}
        />
      )}
      {group && settings && (
        <GroupSettings
          group={group}
          close={() => setSettings(false)}
          update={async (data) => {
            const r = await fetch(`${API}/groups/${group.id}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(data),
            });
            if (!r.ok) throw Error(await detail(r, "Could not save settings."));
            const next = (await r.json()) as Group;
            setGroups((current) =>
              current.map((x) => (x.id === next.id ? next : x)),
            );
          }}
          deleted={() => {
            setGroups((x) => x.filter((x) => x.id !== group.id));
            setSpace(user?.personal_space_id ?? "");
            setSettings(false);
          }}
        />
      )}
      {action && (
        <ActionSheet
          item={action}
          close={() => setAction(null)}
          edit={() => {
            setAction(null);
            setEditing(action);
          }}
          history={() => {
            setAction(null);
            setHistoryItem(action);
          }}
          duplicate={() => void duplicate(action)}
          archive={() => void archive(action)}
          restore={() => void restore(action)}
        />
      )}{" "}
      {logging && (
        <LogForm item={logging} close={() => setLogging(null)} done={log} />
      )}{" "}
      {editing && (
        <EditForm
          item={editing}
          close={() => setEditing(null)}
          done={async (data) => {
            const r = await fetch(`${API}/promises/${editing.id}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(data),
            });
            if (!r.ok) throw Error(await detail(r, "Could not edit promise."));
            setEditing(null);
            void load();
          }}
        />
      )}
      {historyItem && <History item={historyItem} close={() => setHistoryItem(null)} />}
      {profile && user && <ProfileSettings user={user} close={() => setProfile(false)} save={async (display_name) => { const response = await fetch(`${API}/me`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name }) }); if (!response.ok) throw Error(await detail(response, "Could not save profile.")); setUser({ ...user, ...(await response.json()) }); setProfile(false); }} logout={logout} />}
    </main>
  );
}
function ProfileSettings({ user, close, save, logout }: { user: User; close: () => void; save: (name: string) => Promise<void>; logout: () => void }) {
  const [name, setName] = useState(user.display_name), [error, setError] = useState(""), [saving, setSaving] = useState(false);
  const submit = async (event: FormEvent) => { event.preventDefault(); setSaving(true); try { await save(name.trim()); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save profile."); } finally { setSaving(false); } };
  return <div className="modal"><form onSubmit={submit}><button className="close" type="button" onClick={close}>×</button><small>PROFILE</small><h2>Your identity</h2>{error && <p className="form-error">{error}</p>}<label>Display name<input value={name} onChange={(event) => setName(event.target.value)} minLength={2} required /></label><p className="form-hint">This name appears on promises you add to a group.</p><Actions close={close} label={saving ? "Saving…" : "Save profile"} disabled={name.trim().length < 2 || saving} /><button className="logout-link" type="button" onClick={logout}>Log out</button></form></div>
}

function Card({
  item,
  manage,
  log,
}: {
  item: Item;
  manage: () => void;
  log: () => void;
}) {
  return (
    <article className={item.completion_percent >= 100 ? "complete" : ""}>
      <div className="card-head">
        <b>{item.category[0]}</b>
        <small>{item.frequency}</small>
        <button
          className="card-menu"
          aria-label="Manage promise"
          onClick={manage}
        >
          •••
        </button>
      </div>
      <h3>{item.title}</h3>
      <p className="promise-owner"><b>{item.owner_name}</b> is showing up for this</p>
      <p>
        {modes[item.tracking_mode]} ·{" "}
        {item.target_value
          ? `${item.current_progress} / ${item.target_value} ${item.unit ?? ""}`
          : item.completion_percent
            ? "Completed this period"
            : "Not completed this period"}
      </p>
      <div className="track">
        <i style={{ width: `${item.completion_percent}%` }} />
      </div>
      <footer>
        <small>{item.completion_percent}% complete</small>
        <button
          disabled={item.is_locked || item.completion_percent >= 100}
          onClick={log}
        >
          {item.is_locked
            ? "Locked"
            : item.tracking_mode === "check_off"
              ? "Mark done"
              : "Log progress"}
        </button>
      </footer>
    </article>
  );
}
function ActionSheet({
  item,
  close,
  edit,
  history,
  duplicate,
  archive,
  restore,
}: {
  item: Item;
  close: () => void;
  edit: () => void;
  history: () => void;
  duplicate: () => void;
  archive: () => void;
  restore: () => void;
}) {
  return (
    <div className="modal">
      <section className="action-sheet">
        <button className="close" onClick={close}>
          ×
        </button>
        <small>MANAGE PROMISE</small>
        <h2>{item.title}</h2>
        <p>
          {item.category} · {modes[item.tracking_mode]}
        </p>
        <button onClick={edit}>
          Edit promise details <span>›</span>
        </button>
        <button onClick={history}>
          View progress &amp; graph <span>›</span>
        </button>
        <button onClick={duplicate}>
          Duplicate promise <span>›</span>
        </button>
        {item.status === "archived" ? <button onClick={restore}>Restore to active promises <span>›</span></button> : <button className="danger" onClick={archive}>Archive promise <span>›</span></button>}
      </section>
    </div>
  );
}
function LogForm({
  item,
  close,
  done,
}: {
  item: Item;
  close: () => void;
  done: (item: Item, value: number, note: string) => Promise<void>;
}) {
  const [value, setValue] = useState(
      item.tracking_mode === "check_off" ? "1" : "",
    ),
    [note, setNote] = useState(""),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await done(item, Number(value), note);
    } catch (x) {
      setError(x instanceof Error ? x.message : "Could not log progress.");
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="modal">
      <form onSubmit={submit}>
        <button className="close" type="button" onClick={close}>
          ×
        </button>
        <small>CHECK IN</small>
        <h2>{item.title}</h2>
        {error && <p className="form-error">{error}</p>}
        <label>
          {item.tracking_mode === "check_off" ? "Complete" : "Progress value"}
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
          />
        </label>
        <label>
          Note <span>(optional)</span>
          <textarea
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="How did it go?"
          />
        </label>
        <Actions
          close={close}
          label={saving ? "Saving…" : "Save check-in"}
          disabled={!Number(value) || saving}
        />
      </form>
    </div>
  );
}
function GroupForm({
  close,
  done,
}: {
  close: () => void;
  done: (name: string, policy: string) => Promise<void>;
}) {
  const [name, setName] = useState(""),
    [policy, setPolicy] = useState("invite_link"),
    [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await done(name.trim(), policy);
    } catch (x) {
      setError(x instanceof Error ? x.message : "Could not create group.");
    }
  };
  return (
    <div className="modal">
      <form onSubmit={submit}>
        <button className="close" type="button" onClick={close}>
          ×
        </button>
        <small>NEW GROUP</small>
        <h2>Create an accountability group</h2>
        {error && <p className="form-error">{error}</p>}
        <label>
          Group name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <label>
          How people join
          <select value={policy} onChange={(e) => setPolicy(e.target.value)}>
            <option value="invite_link">Anyone with invite link</option>
            <option value="admin_approval">Admin approval required</option>
          </select>
        </label>
        <Actions
          close={close}
          label="Create group"
          disabled={name.trim().length < 3}
        />
      </form>
    </div>
  );
}
function GroupSettings({
  group,
  close,
  update,
  deleted,
}: {
  group: Group;
  close: () => void;
  update: (data: Record<string, string>) => Promise<void>;
  deleted: () => void;
}) {
  const [name, setName] = useState(group.name),
    [policy, setPolicy] = useState(group.join_policy),
    [zone, setZone] = useState(group.timezone),
    [members, setMembers] = useState<Member[]>([]),
    [requests, setRequests] = useState<Join[]>([]),
    [error, setError] = useState(""),
    [confirmDelete, setConfirmDelete] = useState(false);
  const refresh = async () => {
    try {
      const [m, r] = await Promise.all([
        fetch(`${API}/groups/${group.id}/members`),
        fetch(`${API}/groups/${group.id}/join-requests`),
      ]);
      if (!m.ok) throw Error(await detail(m, "Could not load members."));
      setMembers(await m.json());
      if (r.ok) setRequests(await r.json());
    } catch (x) {
      setError(
        x instanceof Error ? x.message : "Could not load group management.",
      );
    }
  };
  useEffect(() => {
    void refresh();
  }, [group.id]);
  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await update({ name: name.trim(), join_policy: policy, timezone: zone });
      close();
    } catch (x) {
      setError(x instanceof Error ? x.message : "Could not save settings.");
    }
  };
  const decide = async (id: string, decision: string) => {
    const r = await fetch(
      `${API}/groups/${group.id}/join-requests/${id}/${decision}`,
      { method: "POST" },
    );
    if (!r.ok) setError(await detail(r, "Could not update request."));
    else void refresh();
  };
  const role = async (id: string, next: string) => {
    const r = await fetch(
      `${API}/groups/${group.id}/members/${id}?role=${next}`,
      { method: "PATCH" },
    );
    if (!r.ok) setError(await detail(r, "Could not change role."));
    else void refresh();
  };
  const remove = async () => {
    const r = await fetch(`${API}/groups/${group.id}`, { method: "DELETE" });
    if (!r.ok) {
      setError(await detail(r, "Could not delete group."));
      return;
    }
    deleted();
  };
  return (
    <div className="modal">
      <section className="settings-panel">
        <button className="close" onClick={close}>
          ×
        </button>
        <small>GROUP SETTINGS</small>
        <h2>{group.name}</h2>
        {error && <p className="form-error">{error}</p>}
        <form onSubmit={save}>
          <label>
            Group name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Join policy
            <select value={policy} onChange={(e) => setPolicy(e.target.value)}>
              <option value="invite_link">Anyone with invite link</option>
              <option value="admin_approval">Admin approval required</option>
            </select>
          </label>
          <label>
            Group time zone
            <input value={zone} onChange={(e) => setZone(e.target.value)} />
          </label>
          <button className="primary" disabled={name.trim().length < 3}>
            Save settings
          </button>
        </form>
        <h3>Members</h3>
        <div className="member-list">
          {members.map((member) => (
            <div key={member.user_id}>
              <span>
                <b>{member.name}</b>
                <small>{member.email}</small>
              </span>
              {group.role === "owner" && member.role !== "owner" ? (
                <select
                  value={member.role}
                  onChange={(e) => void role(member.user_id, e.target.value)}
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </select>
              ) : (
                <em>{member.role}</em>
              )}
            </div>
          ))}
        </div>
        {requests.length > 0 && (
          <>
            <h3>Join requests</h3>
            {requests.map((request) => (
              <div className="request" key={request.id}>
                <span>
                  <b>{request.name}</b>
                  <small>{request.email}</small>
                </span>
                <button onClick={() => void decide(request.id, "approve")}>
                  Approve
                </button>
                <button onClick={() => void decide(request.id, "decline")}>
                  Decline
                </button>
              </div>
            ))}
          </>
        )}
        {group.role === "owner" && (
          <div className="danger-zone">
            <h3>Delete group</h3>
            <p>
              This permanently deletes its promises, progress, invitations, and
              members.
            </p>
            {confirmDelete ? (
              <button className="danger-button" onClick={() => void remove()}>
                Confirm permanent deletion
              </button>
            ) : (
              <button
                className="danger-button"
                onClick={() => setConfirmDelete(true)}
              >
                Delete this group
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
function EditForm({
  item,
  close,
  done,
}: {
  item: Item;
  close: () => void;
  done: (data: Record<string, unknown>) => Promise<void>;
}) {
  const [title, setTitle] = useState(item.title),
    [category, setCategory] = useState(item.category),
    [frequency, setFrequency] = useState(item.frequency),
    [target, setTarget] = useState(String(item.target_value ?? "")),
    [unit, setUnit] = useState(item.unit ?? ""),
    [why, setWhy] = useState(item.why_it_matters ?? ""),
    [error, setError] = useState("");
  const numeric = item.tracking_mode !== "check_off";
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await done({
        title: title.trim(),
        category,
        frequency,
        target_value: numeric ? Number(target) : undefined,
        unit: numeric ? unit.trim() : undefined,
        why_it_matters: why || null,
      });
    } catch (x) {
      setError(x instanceof Error ? x.message : "Could not edit promise.");
    }
  };
  return (
    <div className="modal">
      <form onSubmit={submit}>
        <button className="close" type="button" onClick={close}>
          ×
        </button>
        <small>PROMISE SETTINGS</small>
        <h2>Edit promise</h2>
        {error && <p className="form-error">{error}</p>}
        <label>
          Promise title
          <input value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <div className="row">
          <label>
            Category
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {["Health", "Fitness", "Learning", "Career", "Personal"].map(
                (x) => (
                  <option key={x}>{x}</option>
                ),
              )}
            </select>
          </label>
          <label>
            Repeat
            <select
              value={frequency}
              onChange={(e) => setFrequency(e.target.value)}
            >
              {["daily", "weekly", "monthly"].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
        </div>
        {numeric && (
          <div className="row">
            <label>
              Target
              <input
                type="number"
                min="0.01"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
            </label>
            <label>
              Unit
              <input value={unit} onChange={(e) => setUnit(e.target.value)} />
            </label>
          </div>
        )}
        <label>
          Why does this matter?
          <textarea
            rows={3}
            value={why}
            onChange={(e) => setWhy(e.target.value)}
          />
        </label>
        <Actions
          close={close}
          label="Save changes"
          disabled={
            title.trim().length < 5 || (numeric && (!target || !unit.trim()))
          }
        />
      </form>
    </div>
  );
}
function History({ item, close }: { item: Item; close: () => void }) {
  const [entries, setEntries] = useState<Entry[]>([]),
    [period, setPeriod] = useState<string | null>(null);
  useEffect(() => {
    void (async () => {
      const r = await fetch(`${API}/promises/${item.id}/history`);
      if (r.ok) {
        const body = await r.json();
        setEntries(body.entries);
        setPeriod(body.period_start);
      }
    })();
  }, [item.id]);
  const relevant = period
      ? entries.filter((x) => x.in_current_period)
      : entries,
    max = Math.max(item.target_value ?? 1, ...relevant.map((x) => period ? x.period_total : x.total), 1),
    points = relevant
      .map(
        (x, i) =>
          `${relevant.length === 1 ? 50 : 6 + (i / (relevant.length - 1)) * 88},${94 - ((period ? x.period_total : x.total) / max) * 84}`,
      )
      .join(" ");
  return (
    <div className="modal">
      <section className="history-panel">
        <button className="close" onClick={close}>
          ×
        </button>
        <small>
          {period ? `CURRENT PERIOD SINCE ${period}` : "PROGRESS HISTORY"}
        </small>
        <h2>{item.title}</h2>
        <div className="chart">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none">
            <line x1="0" y1="94" x2="100" y2="94" />
            {points && <polyline points={points} />}
          </svg>
        </div>
        <div className="history-list">
          {entries.length ? (
            entries
              .slice()
              .reverse()
              .map((x) => (
                <div key={x.id}>
                  <b>
                    +{x.value} {item.unit ?? ""}
                  </b>
                  <span>
                    {new Date(x.completed_at).toLocaleString()}
                    {x.note ? ` · ${x.note}` : ""}
                    {period && !x.in_current_period ? " · earlier period" : ""}
                  </span>
                </div>
              ))
          ) : (
            <p>No check-ins yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}
function Actions({
  close,
  label,
  disabled,
}: {
  close: () => void;
  label: string;
  disabled: boolean;
}) {
  return (
    <div className="actions">
      <button type="button" onClick={close}>
        Cancel
      </button>
      <button className="primary" disabled={disabled}>
        {label}
      </button>
    </div>
  );
}
function PromiseForm({
  space,
  close,
  done,
}: {
  space: string;
  close: () => void;
  done: () => void;
}) {
  const [mode, setMode] = useState("check_off"),
    [title, setTitle] = useState(""),
    [unit, setUnit] = useState(""),
    [schedule, setSchedule] = useState("recurring"),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  const numeric = mode !== "check_off";
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (schedule === "date_range" && (!start || !end || end < start)) {
      setError("Choose a valid start and end date.");
      return;
    }
    setSaving(true);
    try {
      const r = await fetch(`${API}/spaces/${space}/promises`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          category: form.get("category"),
          tracking_mode: mode,
          target_value: numeric ? Number(form.get("target")) : null,
          unit: numeric ? unit.trim() : null,
          schedule_type: schedule,
          frequency: schedule === "date_range" ? "date_range" : form.get("frequency"),
          start_date: schedule === "date_range" ? start : null,
          end_date: schedule === "date_range" ? end : null,
          why_it_matters: form.get("why") || null,
        }),
      });
      if (!r.ok) throw Error(await detail(r, "Could not create promise."));
      done();
    } catch (x) {
      setError(x instanceof Error ? x.message : "Could not create promise.");
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="modal">
      <form onSubmit={submit}>
        <button className="close" type="button" onClick={close}>
          ×
        </button>
        <small>NEW PROMISE</small>
        <h2>What will you show up for?</h2>
        {error && <p className="form-error">{error}</p>}
        <label>
          Promise title
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </label>
        <div className="row">
          <label>
            Category
            <select name="category">
              {["Health", "Fitness", "Learning", "Career", "Personal"].map(
                (x) => (
                  <option key={x}>{x}</option>
                ),
              )}
            </select>
          </label>
          <label>
            Track it by
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              {Object.entries(modes).map(([v, n]) => (
                <option key={v} value={v}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
        {numeric && (
          <div className="row">
            <label>
              Target
              <input
                name="target"
                type="number"
                min="0.01"
                defaultValue="1"
                required
              />
            </label>
            <label>
              Unit
              <input
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                required
              />
            </label>
          </div>
        )}
        <div className="row">
          <label>
            Promise type
            <select value={schedule} onChange={(e) => { setSchedule(e.target.value); setStart(""); setEnd(""); }}>
              <option value="recurring">Recurring</option>
              <option value="date_range">Date range</option>
            </select>
          </label>
          <label>
            Repeat
            <select name="frequency" disabled={schedule === "date_range"}>
              <option>daily</option>
              <option>weekly</option>
              <option>monthly</option>
            </select>
          </label>
        </div>
        {schedule === "date_range" && <div className="row"><label>Start date<input type="date" value={start} onChange={(e) => { setStart(e.target.value); if (end && end < e.target.value) setEnd(""); }} required /></label><label>End date<input type="date" value={end} onChange={(e) => setEnd(e.target.value)} min={start || undefined} disabled={!start} required /></label></div>}
        <label>
          Why does this matter?
          <textarea name="why" rows={3} />
        </label>
        <Actions
          close={close}
          label={saving ? "Creating…" : "Create promise"}
          disabled={
            title.trim().length < 5 || (numeric && !unit.trim()) || saving
          }
        />
      </form>
    </div>
  );
}
