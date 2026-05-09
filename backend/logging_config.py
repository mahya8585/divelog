"""
Application Insights ログ設定モジュール

- WARNING 以上（WARNING / ERROR）のログのみを Application Insights へ転送する。
- ログフォーマットはフロントエンド・バックエンド・Functions 全体で統一する。
  形式: YYYY-MM-DDTHH:MM:SS [LEVEL] logger_name: message
- APPLICATIONINSIGHTS_CONNECTION_STRING 未設定時は Application Insights 送信をスキップする。
"""

import logging
import os

# 全体統一ログフォーマット
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def configure_logging(app=None) -> None:
    """ロギングを設定する。

    - 最小ログレベルを WARNING に設定する（WARNING・ERROR のみ収集）。
    - 全体で統一したログフォーマットを適用する。
    - APPLICATIONINSIGHTS_CONNECTION_STRING が設定されている場合は
      Azure Monitor OpenTelemetry 経由で Application Insights へ転送する。

    Args:
        app: Flask アプリケーションインスタンス（省略可）。
    """
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # ルートロガーを WARNING 以上に設定
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)

    # 既存ハンドラーにフォーマッターを適用
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

    # コンソールハンドラーが未設定の場合は追加
    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.WARNING)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    # Application Insights 設定
    conn_str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if conn_str:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor
            configure_azure_monitor(connection_string=conn_str)
            # OpenTelemetry SDK 設定後もルートレベルを WARNING に維持
            logging.getLogger().setLevel(logging.WARNING)
        except ImportError:
            logging.getLogger(__name__).warning(
                "azure-monitor-opentelemetry がインストールされていません。"
                "Application Insights へのログ送信をスキップします。"
            )

    # Flask アプリケーションロガーの設定
    if app is not None:
        app.logger.setLevel(logging.WARNING)
        for handler in app.logger.handlers:
            handler.setFormatter(formatter)
