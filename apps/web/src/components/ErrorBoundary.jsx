import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '40px',
          textAlign: 'center',
          fontFamily: 'system-ui, sans-serif',
          maxWidth: '600px',
          margin: '60px auto',
        }}>
          <h1 style={{ color: '#dc2626', marginBottom: '16px' }}>
            Something went wrong
          </h1>
          <p style={{ color: '#6b7280', marginBottom: '24px' }}>
            An unexpected error occurred while rendering this page.
          </p>
          <details style={{
            background: '#f9fafb',
            border: '1px solid #e5e7eb',
            borderRadius: '8px',
            padding: '16px',
            textAlign: 'left',
            marginBottom: '24px',
          }}>
            <summary style={{ cursor: 'pointer', fontWeight: '600' }}>
              Error details
            </summary>
            <pre style={{
              marginTop: '8px',
              fontSize: '13px',
              color: '#374151',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}>
              {this.state.error?.toString()}
              {this.state.errorInfo?.componentStack}
            </pre>
          </details>
          <button
            onClick={() => window.location.reload()}
            style={{
              background: '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              padding: '10px 24px',
              fontSize: '14px',
              cursor: 'pointer',
            }}
          >
            Reload Page
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
