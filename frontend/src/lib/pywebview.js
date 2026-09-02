const BRIDGE_TIMEOUT_MS = 2500

let bridgePromise

export function waitForBridge(timeout = BRIDGE_TIMEOUT_MS) {
  if (window.pywebview?.api) {
    return Promise.resolve(window.pywebview.api)
  }
  if (bridgePromise) return bridgePromise

  bridgePromise = new Promise((resolve, reject) => {
    let timer
    const finish = () => {
      if (!window.pywebview?.api) return
      window.removeEventListener('pywebviewready', finish)
      clearTimeout(timer)
      resolve(window.pywebview.api)
    }

    window.addEventListener('pywebviewready', finish, { once: true })
    timer = window.setTimeout(() => {
      window.removeEventListener('pywebviewready', finish)
      reject(
        new Error(
          'Desktop bridge unavailable. In development, build the app and launch python desktop_app.py to run generation.',
        ),
      )
    }, timeout)
  })
  return bridgePromise
}

export async function invokeBridge(method, ...args) {
  const api = await waitForBridge()
  const target = api[method]
  if (typeof target !== 'function') {
    throw new Error(`Desktop bridge method is unavailable: ${method}`)
  }
  return target(...args)
}
