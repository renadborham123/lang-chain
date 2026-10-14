import { FormEvent, useMemo, useState } from 'react'
import { ArrowLeft, Check, Eye, EyeOff, Mail, ShieldCheck } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { BrandLogo, Button, FormField } from './ui'
import { api } from './employment-api'

type AuthMode = 'login' | 'signup' | 'forgot-password' | 'reset-password'
type AuthUser = { name: string; email: string; avatar_url?: string; locale?: 'en' | 'ar' }

export function AuthPage({ mode, knownName, onComplete }: { mode: AuthMode; knownName?: string; onComplete: (identity: { name: string; email: string; avatarUrl?: string; locale?: 'en' | 'ar' }) => void }) {
  const navigate = useNavigate()
  const [name, setName] = useState(knownName || '')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [recoverySent, setRecoverySent] = useState(false)
  const [resetComplete, setResetComplete] = useState(false)
  const [rememberMe, setRememberMe] = useState(true)
  const title = mode === 'login' ? 'Sign in to your workspace' : mode === 'signup' ? 'Create your Wazzefni workspace' : mode === 'reset-password' ? 'Choose a new password' : 'Reset your password'
  const copy = mode === 'login'
    ? 'Continue your qualification plan, skill proof, and applications in one place.'
    : mode === 'signup'
      ? 'Start with a private workspace that keeps every career fact under your control.'
      : mode === 'reset-password' ? 'Set a new password for your workspace.' : 'Enter your email to receive a secure password-reset link.'
  const passwordStrength = useMemo(() => {
    let score = 0
    if (password.length >= 8) score++
    if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++
    if (/\d/.test(password) || /[^A-Za-z0-9]/.test(password)) score++
    return score
  }, [password])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (mode !== 'reset-password' && (!email.trim() || !email.includes('@'))) { setError('Enter a valid email address.'); return }
    if (mode === 'signup' && name.trim().length < 2) { setError('Enter the name you want shown in Wazzefni.'); return }
    if (!['forgot-password'].includes(mode) && (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password))) { setError('Use at least 8 characters with a letter and a number.'); return }
    setBusy(true)
    try {
      if (mode === 'forgot-password') {
        const result = await api<{ development_token?: string }>('/auth/password/forgot', { method: 'POST', body: JSON.stringify({ email: email.trim().toLowerCase() }) })
        if (result.development_token) localStorage.setItem('wazzefni-development-reset-token', result.development_token)
        setRecoverySent(true)
        return
      }
      if (mode === 'reset-password') {
        const token = new URLSearchParams(window.location.search).get('token') || localStorage.getItem('wazzefni-development-reset-token') || ''
        if (!token) throw new Error('This reset link is missing or invalid.')
        await api('/auth/password/reset', { method: 'POST', body: JSON.stringify({ token, password }) })
        localStorage.removeItem('wazzefni-development-reset-token')
        setResetComplete(true)
        return
      }
      const user = await api<AuthUser>(mode === 'signup' ? '/auth/signup' : '/auth/login', {
        method: 'POST',
        body: JSON.stringify(mode === 'signup'
          ? { name: name.trim(), email: email.trim().toLowerCase(), password }
          : { email: email.trim().toLowerCase(), password, remember_me: rememberMe }),
      })
      onComplete({ name: user.name, email: user.email, avatarUrl: user.avatar_url, locale: user.locale })
      navigate('/today')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not open the workspace.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="auth-page">
    <section className="auth-story" aria-label="About Wazzefni">
      <BrandLogo/>
      <div className="auth-story-copy">
        <p>YOUR AI QUALIFICATION AGENT</p>
        <h1>Get ready for work, step by step.</h1>
        <span>Diagnose what is missing, build proof, update your CV, then apply when the evidence is ready.</span>
        <ul>
          <li><i><Check size={15}/></i>A personal qualification to-do list</li>
          <li><i><Check size={15}/></i>Skill proof before a CV claim</li>
          <li><i><Check size={15}/></i>Human approval before external actions</li>
        </ul>
      </div>
      <img src="/jobflow-assistant.svg" alt="Wazzefni assistant helping with a career workflow"/>
      <small><ShieldCheck size={14}/> Your data stays in your workspace.</small>
    </section>

    <section className="auth-form-panel">
      <div className="auth-mobile-brand"><BrandLogo/></div>
      <form className="auth-form" onSubmit={submit} noValidate>
        {(mode === 'forgot-password' || mode === 'reset-password') && <Link className="auth-back" to="/login"><ArrowLeft size={15}/> Back to sign in</Link>}
        <div className="auth-heading"><span>Secure workspace</span><h2>{title}</h2><p>{copy}</p></div>
        {resetComplete ? <div className="auth-success"><ShieldCheck size={21}/><div><b>Password updated</b><p>Your new password is active. <Link to="/login">Sign in now</Link>.</p></div></div> : recoverySent ? <div className="auth-success"><Mail size={21}/><div><b>Check your email</b><p>If this email belongs to an account, a secure reset link has been created.</p>{localStorage.getItem('wazzefni-development-reset-token') && <Link to="/reset-password">Continue locally</Link>}</div></div> : <>
          {mode === 'signup' && <FormField label="Full name"><input autoComplete="name" value={name} onChange={event => setName(event.target.value)} placeholder="Your name"/></FormField>}
          {mode !== 'reset-password' && <FormField label="Email address"><input autoComplete="email" inputMode="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="you@company.com"/></FormField>}
          {mode !== 'forgot-password' && <FormField label={mode === 'reset-password' ? 'New password' : 'Password'} hint={mode === 'signup' || mode === 'reset-password' ? 'Use 8+ characters with a mix of letters and numbers.' : undefined}>
            <span className="password-input"><input autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} type={showPassword ? 'text' : 'password'} value={password} onChange={event => setPassword(event.target.value)} placeholder="Enter your password"/><button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff size={17}/> : <Eye size={17}/>}</button></span>
          </FormField>}
          {(mode === 'signup' || mode === 'reset-password') && <div className="password-strength" aria-label={`Password strength ${passwordStrength} of 3`}><i className={passwordStrength > 0 ? 'active' : ''}/><i className={passwordStrength > 1 ? 'active' : ''}/><i className={passwordStrength > 2 ? 'active' : ''}/></div>}
          {mode === 'login' && <div className="auth-options"><label><input type="checkbox" checked={rememberMe} onChange={event => setRememberMe(event.target.checked)}/> Keep me signed in</label><Link to="/forgot-password">Forgot password?</Link></div>}
          {error && <p className="auth-error" role="alert">{error}</p>}
          <Button type="submit" disabled={busy} trailing>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : mode === 'signup' ? 'Create workspace' : mode === 'reset-password' ? 'Update password' : 'Send recovery link'}</Button>
        </>}
        {(mode === 'login' || mode === 'signup') && <p className="auth-switch">{mode === 'login' ? 'New to Wazzefni?' : 'Already have a workspace?'} <Link to={mode === 'login' ? '/signup' : '/login'}>{mode === 'login' ? 'Create an account' : 'Sign in'}</Link></p>}
      </form>
      <footer>By continuing, you agree to the Terms and acknowledge the Privacy Policy.</footer>
    </section>
  </main>
}
