import { useId, useRef, useState } from 'react'

export default function HelpTip({ children, text }) {
  const id = useId()
  const button = useRef(null)
  const [position, setPosition] = useState(null)
  const content = children ?? text
  const place = () => {
    const rect = button.current.getBoundingClientRect()
    const width = Math.min(274, window.innerWidth - 24)
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))
    const below = window.innerHeight - rect.bottom >= 150
    setPosition({ left, width, ...(below ? { top: rect.bottom + 8 } : { bottom: window.innerHeight - rect.top + 8 }) })
  }
  return (
    <span className="help-tip" onMouseEnter={place} onFocus={place}>
      <button ref={button} type="button" className="help-tip-button" aria-label={`Help: ${content}`} aria-describedby={id}>?</button>
      <span className="help-tip-content" role="tooltip" id={id} style={position}>{content}</span>
    </span>
  )
}
