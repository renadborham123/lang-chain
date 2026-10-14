import { FormEvent, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Bot, Check, ChevronRight, Globe2, ImagePlus, LockKeyhole, LogOut, MonitorCog, SlidersHorizontal, Trash2, UserRound } from 'lucide-react'
import { api } from './employment-api'
import { Button, FormField, SectionTitle, Toggle, UserAvatar } from './ui'
import { useI18n } from './i18n'

type AccountResponse = {
  user_id: string
  name: string
  email: string
  avatar_url: string
  locale: string
  country: string
  profile: Record<string, unknown>
  preferences: Record<string, unknown>
}

const settingSections = [
  { id: 'account', label: 'Account', icon: UserRound },
  { id: 'preferences', label: 'Preferences', icon: SlidersHorizontal },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'workspace', label: 'Workspace & AI', icon: MonitorCog },
] as const

export function SettingsPage({ modelLabel, onOpenModel, onSignOut, onIdentityChange }: { modelLabel: string; onOpenModel: () => void; onSignOut: () => void | Promise<void>; onIdentityChange?: (identity: { name: string; email: string; avatarUrl?: string }) => void }) {
  const { locale, setLocale } = useI18n()
  const queryClient = useQueryClient()
  const profile = useQuery({ queryKey: ['account'], queryFn: () => api<AccountResponse>('/auth/me') })
  const profileUpdate = useMutation({ mutationFn: (payload: Record<string, unknown>) => api('/profile', { method: 'PATCH', body: JSON.stringify(payload) }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['account'] }) })
  const accountUpdate = useMutation({ mutationFn: (payload: Record<string, unknown>) => api<AccountResponse>('/auth/account', { method: 'PATCH', body: JSON.stringify(payload) }), onSuccess: data => { queryClient.setQueryData(['account'], data); onIdentityChange?.({ name: data.name, email: data.email, avatarUrl: data.avatar_url }) } })
  const avatarUpdate = useMutation({ mutationFn: async (file: File) => { const body = new FormData(); body.append('avatar', file); return api<AccountResponse>('/auth/avatar', { method: 'POST', body }) }, onSuccess: data => { queryClient.setQueryData(['account'], data); onIdentityChange?.({ name: data.name, email: data.email, avatarUrl: data.avatar_url }) } })
  const avatarDelete = useMutation({ mutationFn: () => api('/auth/avatar', { method: 'DELETE' }), onSuccess: () => { queryClient.setQueryData<AccountResponse>(['account'], current => current ? { ...current, avatar_url: '' } : current); onIdentityChange?.({ name, email, avatarUrl: '' }) } })
  const [section, setSection] = useState<(typeof settingSections)[number]['id']>('account')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone)
  const [phone, setPhone] = useState('')
  const [headline, setHeadline] = useState('')
  const [profileLocation, setProfileLocation] = useState('')
  const [bio, setBio] = useState('')
  const [location, setLocation] = useState(localStorage.getItem('wazzefni-target-location') || localStorage.getItem('jobflow-target-location') || 'Cairo')
  const [remote, setRemote] = useState(false)
  const [density, setDensity] = useState(localStorage.getItem('wazzefni-density') || localStorage.getItem('jobflow-density') || 'comfortable')
  const [notifications, setNotifications] = useState(() => {
    try { return JSON.parse(localStorage.getItem('wazzefni-notifications') || localStorage.getItem('jobflow-notifications') || '{"application":true,"interview":true,"digest":false}') }
    catch { return { application: true, interview: true, digest: false } }
  })

  useEffect(() => {
    if (!profile.data) return
    setName(profile.data.name)
    setEmail(profile.data.email)
    setTimezone(String(profile.data.profile.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone))
    setPhone(String(profile.data.profile.phone || ''))
    setHeadline(String(profile.data.profile.headline || ''))
    setProfileLocation(String(profile.data.profile.location || ''))
    setBio(String(profile.data.profile.bio || ''))
    setRemote(Boolean(profile.data.preferences.remote_only))
  }, [profile.data])

  function saveAccount(event: FormEvent) {
    event.preventDefault()
    accountUpdate.mutate({ name: name.trim(), email: email.trim().toLowerCase(), timezone, phone, headline, location: profileLocation, bio })
  }

  function savePreferences() {
    localStorage.setItem('wazzefni-target-location', location)
    profileUpdate.mutate({ preferences: { remote_only: remote, default_location: location } })
  }

  function chooseDensity(value: string) {
    setDensity(value)
    localStorage.setItem('wazzefni-density', value)
    document.documentElement.dataset.density = value
  }

  function setNotification(key: string, value: boolean) {
    const next = { ...notifications, [key]: value }
    setNotifications(next)
    localStorage.setItem('wazzefni-notifications', JSON.stringify(next))
  }

  function chooseLocale(nextLocale: 'en' | 'ar') {
    setLocale(nextLocale)
    profileUpdate.mutate({ locale: nextLocale })
  }

  const profileName = name || 'Wazzefni user'
  return <section className="settings-workspace">
    <aside className="settings-index">
      <div className="settings-person"><UserAvatar name={profileName} src={profile.data?.avatar_url} size="large"/><div><b>{profileName}</b><span>{email || 'Private workspace'}</span></div></div>
      <nav aria-label="Settings sections">{settingSections.map(item => { const Icon = item.icon; return <button className={section === item.id ? 'active' : ''} onClick={() => setSection(item.id)} key={item.id}><Icon size={17}/><span>{item.label}</span><ChevronRight size={15}/></button> })}</nav>
      <button className="settings-signout" onClick={onSignOut}><LogOut size={16}/> Sign out</button>
    </aside>

    <div className="settings-content">
      {section === 'account' && <>
        <SectionTitle eyebrow="ACCOUNT" title="Profile and identity" copy="This information personalizes the workspace. It is never invented from application data."/>
        <div className="account-avatar-editor">
          <UserAvatar name={profileName} src={profile.data?.avatar_url} size="large"/>
          <div><b>Profile photo</b><small>PNG, JPG, or WebP. Maximum 5 MB.</small><span><label className="avatar-upload-action"><ImagePlus size={15}/> {avatarUpdate.isPending ? 'Uploading…' : 'Upload photo'}<input type="file" accept="image/png,image/jpeg,image/webp" disabled={avatarUpdate.isPending} onChange={event => { const file = event.target.files?.[0]; if (file) avatarUpdate.mutate(file); event.currentTarget.value = '' }}/></label>{profile.data?.avatar_url && <button className="avatar-remove-action" type="button" onClick={() => avatarDelete.mutate()} disabled={avatarDelete.isPending}><Trash2 size={14}/>Remove</button>}</span></div>
        </div>
        {(avatarUpdate.error || avatarDelete.error) && <p className="settings-error">{(avatarUpdate.error || avatarDelete.error)?.message}</p>}
        <form className="settings-form" onSubmit={saveAccount}>
          <div className="settings-form-grid"><FormField label="Display name"><input value={name} onChange={event => setName(event.target.value)} placeholder="Your name"/></FormField><FormField label="Email address"><input inputMode="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="you@company.com"/></FormField></div>
          <div className="settings-form-grid"><FormField label="Professional headline"><input value={headline} onChange={event => setHeadline(event.target.value)} placeholder="e.g. Product designer"/></FormField><FormField label="Phone number"><input inputMode="tel" value={phone} onChange={event => setPhone(event.target.value)} placeholder="+20 100 000 0000"/></FormField></div>
          <FormField label="Location"><input value={profileLocation} onChange={event => setProfileLocation(event.target.value)} placeholder="City, country"/></FormField>
          <FormField label="Time zone" hint="Used for interview reminders and follow-up timing."><select value={timezone} onChange={event => setTimezone(event.target.value)}><option value="Africa/Cairo">Africa/Cairo</option><option value="Asia/Riyadh">Asia/Riyadh</option><option value="Asia/Dubai">Asia/Dubai</option><option value="Europe/London">Europe/London</option><option value="America/New_York">America/New_York</option></select></FormField>
          <FormField label="Short bio" hint="A concise summary used to personalize recommendations."><textarea rows={4} value={bio} onChange={event => setBio(event.target.value)} placeholder="What should Wazzefni know about your goals and experience?"/></FormField>
          {accountUpdate.error && <p className="settings-error">{accountUpdate.error.message}</p>}
          <div className="settings-save-row"><span>{accountUpdate.isSuccess && <><Check size={14}/> Changes saved</>}</span><Button type="submit" disabled={accountUpdate.isPending}>{accountUpdate.isPending ? 'Saving…' : 'Save changes'}</Button></div>
        </form>
      </>}

      {section === 'preferences' && <>
        <SectionTitle eyebrow="PREFERENCES" title="Search defaults" copy="Set stable defaults once. You can still override them for any individual search."/>
        <div className="settings-form">
          <div className="settings-form-grid"><FormField label="Default location"><input value={location} onChange={event => setLocation(event.target.value)} placeholder="City, country, or Remote"/></FormField><FormField label="Market"><select value={profile.data?.country || 'EG'} onChange={event => profileUpdate.mutate({ country: event.target.value })}><option value="EG">Egypt</option><option value="SA">Saudi Arabia</option><option value="AE">United Arab Emirates</option></select></FormField></div>
          <Toggle checked={remote} onChange={setRemote} label="Prioritize remote roles" description="Ranks remote opportunities first without hiding strong local matches."/>
          <div className="settings-save-row"><span/><Button onClick={savePreferences} disabled={profileUpdate.isPending}>Save preferences</Button></div>
        </div>
        <SectionTitle eyebrow="LANGUAGE" title="Interface language" copy="Changes labels and reading direction across the product."/>
        <div className="segmented-control"><button className={locale === 'en' ? 'active' : ''} onClick={() => chooseLocale('en')}><Globe2 size={16}/>English</button><button className={locale === 'ar' ? 'active' : ''} onClick={() => chooseLocale('ar')}>Arabic</button></div>
      </>}

      {section === 'notifications' && <>
        <SectionTitle eyebrow="NOTIFICATIONS" title="Only the updates that matter" copy="Wazzefni stays quiet unless a status changes or your action is required."/>
        <div className="settings-toggle-list"><Toggle checked={notifications.application} onChange={value => setNotification('application', value)} label="Application updates" description="Replies, status changes, and forms that need input."/><Toggle checked={notifications.interview} onChange={value => setNotification('interview', value)} label="Interview reminders" description="Reminders before scheduled interviews and preparation sessions."/><Toggle checked={notifications.digest} onChange={value => setNotification('digest', value)} label="Weekly progress digest" description="A concise summary of applications, conversion, and next actions."/></div>
      </>}

      {section === 'workspace' && <>
        <SectionTitle eyebrow="WORKSPACE" title="Appearance and runtime" copy="Tune information density and the AI runtime without changing your underlying career data."/>
        <div className="setting-block"><div><b>Information density</b><p>Comfortable works best on touch devices. Compact fits more rows on larger screens.</p></div><div className="density-options"><button className={density === 'comfortable' ? 'active' : ''} onClick={() => chooseDensity('comfortable')}>Comfortable</button><button className={density === 'compact' ? 'active' : ''} onClick={() => chooseDensity('compact')}>Compact</button></div></div>
        <div className="setting-block ai-runtime"><span><Bot size={21}/></span><div><b>AI runtime</b><p>{modelLabel}</p></div><Button variant="secondary" onClick={onOpenModel}>Configure</Button></div>
        <SectionTitle eyebrow="PRIVACY" title="Control stays with you" copy="External submission, messaging, calendar changes, and offer responses always require approval."/>
        <div className="privacy-setting"><LockKeyhole size={20}/><div><b>Database-backed private account</b><p>Passwords are hashed, sessions stay in an HttpOnly cookie, and profile data is isolated by your account ID.</p></div></div>
      </>}
    </div>
  </section>
}
