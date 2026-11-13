interface ErrorModalProps {
  isOpen: boolean
  title: string
  message: string
  onClose: () => void
}

function ErrorModal({ isOpen, title, message, onClose }: ErrorModalProps) {
  if (!isOpen) return null

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div style={styles.header}>
          <div style={styles.icon}>⚠️</div>
          <h3 style={styles.title}>{title}</h3>
        </div>
        <p style={styles.message}>{message}</p>
        <button onClick={onClose} style={styles.button}>
          OK
        </button>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(0, 0, 0, 0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    backdropFilter: 'blur(4px)',
  },
  modal: {
    background: '#1a1a2e',
    borderRadius: '16px',
    padding: '32px',
    maxWidth: '400px',
    width: '90%',
    textAlign: 'center' as const,
    border: '1px solid rgba(255,255,255,0.1)',
    boxShadow: '0 25px 50px rgba(0,0,0,0.5)',
  },
  header: {
    marginBottom: '16px',
  },
  icon: {
    fontSize: '48px',
    marginBottom: '12px',
  },
  title: {
    color: '#ffffff',
    fontSize: '20px',
    fontWeight: 600,
    margin: 0,
  },
  message: {
    color: '#b8b8d0',
    fontSize: '14px',
    lineHeight: '1.6',
    margin: '0 0 24px 0',
  },
  button: {
    background: 'linear-gradient(135deg, #667eea, #764ba2)',
    color: '#fff',
    border: 'none',
    borderRadius: '10px',
    padding: '12px 32px',
    fontSize: '15px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'opacity 0.2s',
  },
}

export default ErrorModal
