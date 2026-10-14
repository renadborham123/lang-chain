import { ButtonHTMLAttributes, ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import { useI18n } from './i18n'

export function BrandLogo({ compact = false }: { compact?: boolean }) {
  const { locale } = useI18n()
  const brandName = locale === 'ar' ? 'وظّفني' : 'Wazzefni'
  return <span className={`ui-brand ${compact ? 'compact' : ''}`} aria-label={brandName}>
    <span className="ui-brand-mark" aria-hidden="true"><i/><i/></span>
    {!compact && <strong>{brandName}</strong>}
  </span>
}

export function UserAvatar({ name, src, size = 'medium' }: { name?: string; src?: string; size?: 'small' | 'medium' | 'large' }) {
  const initials = (name || 'Wazzefni user')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0]?.toUpperCase())
    .join('') || 'JU'
  return <span className={`ui-avatar ${size}`} aria-hidden="true">{initials}{src && <img src={src} alt="" onError={event => { event.currentTarget.hidden = true }}/>}</span>
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger'
  trailing?: boolean
}

export function Button({ variant = 'primary', trailing = false, children, className = '', ...props }: ButtonProps) {
  return <button className={`ui-button ${variant} ${className}`.trim()} {...props}>
    {children}{trailing && <ArrowRight size={16}/>}
  </button>
}

export function FormField({ label, hint, error, children }: { label: string; hint?: string; error?: string; children: ReactNode }) {
  return <label className={`ui-field ${error ? 'has-error' : ''}`}>
    <span>{label}</span>
    {children}
    {(error || hint) && <small>{error || hint}</small>}
  </label>
}

export function Toggle({ checked, onChange, label, description }: { checked: boolean; onChange: (checked: boolean) => void; label: string; description?: string }) {
  return <label className="ui-toggle-row">
    <span><b>{label}</b>{description && <small>{description}</small>}</span>
    <input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)}/>
    <i aria-hidden="true"/>
  </label>
}

export function SectionTitle({ eyebrow, title, copy, action }: { eyebrow?: string; title: string; copy?: string; action?: ReactNode }) {
  return <header className="ui-section-title">
    <div>{eyebrow && <p>{eyebrow}</p>}<h2>{title}</h2>{copy && <span>{copy}</span>}</div>
    {action}
  </header>
}
