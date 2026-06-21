import { useState } from 'react'
import { Loader2, LogIn, UserPlus } from 'lucide-react'
import { authLogin, authRegister, type AuthUser } from '../api/client'

interface Props {
  onAuthed: (user: AuthUser) => void
}

export default function AuthScreen({ onAuthed }: Props) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!username.trim() || !password) return
    setBusy(true)
    setError(null)
    try {
      const user = mode === 'login'
        ? await authLogin(username.trim(), password)
        : await authRegister(username.trim(), password)
      onAuthed(user)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full flex items-center justify-center bg-ink-900 p-4">
      <div className="w-full max-w-sm bg-ink-800 border border-ink-600 rounded-2xl shadow-2xl p-7">
        <div className="text-center mb-6">
          <div className="text-lg font-semibold text-gray-100">AI Конструкторское бюро</div>
          <div className="text-[12px] text-faint mt-1">
            {mode === 'login' ? 'Вход в систему' : 'Регистрация'}
          </div>
        </div>

        <div className="space-y-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Логин"
            autoFocus
            className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2.5 text-sm text-gray-100 placeholder:text-faint focus:outline-none focus:border-clay-400"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
            placeholder="Пароль"
            className="w-full bg-ink-900 border border-ink-500 rounded-lg px-3 py-2.5 text-sm text-gray-100 placeholder:text-faint focus:outline-none focus:border-clay-400"
          />

          {error && <div className="text-[12px] text-red-300">{error}</div>}

          <button
            onClick={submit}
            disabled={busy || !username.trim() || !password}
            className="w-full py-2.5 bg-clay-500 hover:bg-clay-400 disabled:opacity-40 text-white rounded-lg text-sm flex items-center justify-center gap-2"
          >
            {busy ? <Loader2 size={15} className="animate-spin" />
              : mode === 'login' ? <LogIn size={15} /> : <UserPlus size={15} />}
            {mode === 'login' ? 'Войти' : 'Зарегистрироваться'}
          </button>
        </div>

        <div className="text-center mt-5 text-[12px] text-faint">
          {mode === 'login' ? 'Нет аккаунта? ' : 'Уже есть аккаунт? '}
          <button
            onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null) }}
            className="text-clay-300 hover:text-clay-200"
          >
            {mode === 'login' ? 'Зарегистрироваться' : 'Войти'}
          </button>
        </div>
        {mode === 'register' && (
          <div className="text-center mt-2 text-[10px] text-faint">
            Первый зарегистрированный пользователь становится администратором.
          </div>
        )}
      </div>
    </div>
  )
}
