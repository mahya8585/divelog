/**
 * Azure Monitor Application Insights モジュール
 *
 * - VITE_APPINSIGHTS_CONNECTION_STRING が設定されている場合のみ有効化する。
 * - 収集対象: ERROR（未処理例外・未処理 Promise 拒否）および WARN レベルのカスタムイベント。
 * - ログフォーマット: バックエンド・Functions と統一した形式で properties に付与する。
 *   { level: 'ERROR'|'WARN', message: string, timestamp: ISO8601 }
 */

import { ApplicationInsights, SeverityLevel } from '@microsoft/applicationinsights-web'

const connectionString = import.meta.env.VITE_APPINSIGHTS_CONNECTION_STRING

/** @type {ApplicationInsights|null} */
let appInsights = null

if (connectionString) {
  appInsights = new ApplicationInsights({
    config: {
      connectionString,
      // ページビュー・AJAX・依存関係の自動収集は無効化し、
      // ERROR/WARN のみ収集する方針に沿う
      enableAutoRouteTracking: false,
      autoTrackPageVisitTime: false,
      disableAjaxTracking: true,
      disableFetchTracking: true,
      disableTelemetry: false,
    },
  })
  appInsights.loadAppInsights()

  // テレメトリ初期化子: Exception と Warning イベント以外を除外する
  appInsights.addTelemetryInitializer((envelope) => {
    const allowed = [
      'Microsoft.ApplicationInsights.Exception',
      'Microsoft.ApplicationInsights.Event',
    ]
    return allowed.includes(envelope.name) ? true : false
  })
}

/**
 * エラー（ERROR レベル）を Application Insights に記録する。
 *
 * @param {Error|unknown} error - 発生したエラー
 * @param {{ [key: string]: string }} [properties] - 追加プロパティ
 */
export function trackError(error, properties = {}) {
  const timestamp = new Date().toISOString()
  const baseProps = { level: 'ERROR', timestamp, ...properties }

  if (!appInsights) {
    console.error(`${timestamp} [ERROR]`, error, baseProps)
    return
  }

  appInsights.trackException({
    exception: error instanceof Error ? error : new Error(String(error)),
    severityLevel: SeverityLevel.Error,
    properties: baseProps,
  })
}

/**
 * 警告（WARN レベル）を Application Insights に記録する。
 *
 * @param {string} message - 警告メッセージ
 * @param {{ [key: string]: string }} [properties] - 追加プロパティ
 */
export function trackWarning(message, properties = {}) {
  const timestamp = new Date().toISOString()
  const baseProps = { level: 'WARN', message, timestamp, ...properties }

  if (!appInsights) {
    console.warn(`${timestamp} [WARN]`, message, baseProps)
    return
  }

  appInsights.trackEvent({
    name: 'Warning',
    properties: baseProps,
  })
}

export { appInsights }
