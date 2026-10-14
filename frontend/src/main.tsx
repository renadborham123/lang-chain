import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@fontsource/cairo/arabic-400.css'
import '@fontsource/cairo/arabic-500.css'
import '@fontsource/cairo/arabic-600.css'
import '@fontsource/cairo/arabic-700.css'
import '@fontsource/cairo/arabic-800.css'
import '@fontsource/cairo/latin-400.css'
import '@fontsource/cairo/latin-500.css'
import '@fontsource/cairo/latin-600.css'
import '@fontsource/cairo/latin-700.css'
import '@fontsource/cairo/latin-800.css'
import '@fontsource/manrope/latin-400.css'
import '@fontsource/manrope/latin-500.css'
import '@fontsource/manrope/latin-600.css'
import '@fontsource/manrope/latin-700.css'
import '@fontsource/manrope/latin-800.css'
import App from './App'
import { I18nProvider } from './i18n'
import './styles.css'
import './rules.css'
import './soft-lime.css'
import './theme.css'
import './responsive.css'

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1 } } })
const legacyKeys = ['locale', 'density', 'target-location', 'saved-jobs', 'application-answers', 'notifications', 'oauth-provider']
legacyKeys.forEach(key => {
  const current = `wazzefni-${key}`
  const legacy = `jobflow-${key}`
  if (localStorage.getItem(current) === null && localStorage.getItem(legacy) !== null) {
    localStorage.setItem(current, localStorage.getItem(legacy)!)
  }
})
const locale = localStorage.getItem('wazzefni-locale') || localStorage.getItem('jobflow-locale') || 'en'
document.documentElement.lang = locale
document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
document.documentElement.dataset.density = localStorage.getItem('wazzefni-density') || localStorage.getItem('jobflow-density') || 'comfortable'

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => undefined))
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><BrowserRouter><QueryClientProvider client={queryClient}><I18nProvider><App /></I18nProvider></QueryClientProvider></BrowserRouter></StrictMode>,
)
