#!/usr/bin/env python3
"""Cat1 Page Monitor — 輕量 MCP Server (stdio JSON-RPC 2.0)。

提供 2 個工具：
1. cat1_diff_page（免費體驗，免 Key 可試）：單頁去雜訊語義比對＋變更摘要＋SHA-256 證據。
2. cat1_schedule_monitor（常駐排程監測，設 Key 閘門）：
   - 無 Key：回傳導流訊息，引導至 https://toplformater.click（USD 29／月，7 天免費試用、免綁卡）。
   - 有 Key：僅做本地格式檢查，不呼叫 Paddle／PayPal、不自創驗證 API、不偽造驗證結果、不在本地假裝排程。
"""

import json
import os
import re
import sys

from engine import compare_pages

SERVER_NAME = "page-monitor-mcp-server"
SERVER_VERSION = "0.1.0"
KEY_REGEX = re.compile(r"^cat1_(?:live|trial)_[A-Za-z0-9]{16,64}$")
PLACEHOLDER_KEYS = {
    "",
    "YOUR_CAT1_KEY_HERE",
    "YOUR_CAT1_KEY_HERE_OPTIONAL",
    "REPLACE_WITH_YOUR_KEY",
}

UPGRADE_URL = "https://toplformater.click"
REFERRAL_MESSAGE = (
    "【Cat1 常駐排程監測 — 需持 Key 啟用】\n"
    "單頁即時去雜訊比對（cat1_diff_page）為免費免 Key 工具；"
    "跨時間軸 7×24 常駐排程巡檢與主動告警（cat1_schedule_monitor）為 Cat1 正式服務功能。\n"
    "請前往 https://toplformater.click 領取正式 API Key（USD 29／月，提供 7 天免費試用、免綁卡）。\n"
    "取得 Key 後，可設定於環境變數 CAT1_API_KEY 或於工具參數 api_key 傳入。"
)

TOOLS = [
    {
        "name": "cat1_diff_page",
        "description": (
            "【免費免 Key】對目標網頁或本地 HTML 執行去雜訊語義正規化與基線比對，"
            "自動濾除動態計數器、相對時間戳與隨機 Nonce，輸出 SHA-256 雜湊證據、變更摘要與 Unified Diff。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_url": {
                    "type": "string",
                    "description": "目標頁面 URL（http/https）、本地檔案路徑（或 file://）或 HTML 字串（T1 當前狀態）。",
                },
                "baseline_source": {
                    "type": "string",
                    "description": "可選：基線頁面 URL、本地檔案路徑或基線 HTML 字串（T0 基線狀態）。",
                },
                "baseline_sha256": {
                    "type": "string",
                    "description": "可選：若僅有基線正規化後之 SHA-256 雜湊值，可傳入此欄位進行雜湊比對。",
                },
            },
            "required": ["target_url"],
        },
    },
    {
        "name": "cat1_schedule_monitor",
        "description": (
            "【需持 Key】申請或檢核 7×24 常駐排程網頁變更監測規則（設 Key 閘門）。"
            "無 Key 時回傳 https://toplformater.click 7 天免綁卡試用與正式 Key 領取導流說明；"
            "持 Key 時僅做本地金鑰格式檢核（不連線驗證、不在本地假裝排程，實際排程由我方自有服務執行）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_url": {
                    "type": "string",
                    "description": "欲持續監測之公開網頁 URL。",
                },
                "interval_minutes": {
                    "type": "integer",
                    "description": "期望巡檢間隔分鐘數（例如 5、15、60）。",
                    "default": 15,
                },
                "alert_email": {
                    "type": "string",
                    "description": "可選：接收變更告警與日期證據包之電子郵件位址。",
                },
                "api_key": {
                    "type": "string",
                    "description": "可選：Cat1 API Key（格式 cat1_trial_... 或 cat1_live_...；若未傳入則讀取環境變數 CAT1_API_KEY）。",
                },
            },
            "required": ["target_url"],
        },
    },
]


def check_key_gate(provided_key=None):
    """執行 Key 閘門檢核：僅做存在性與本地格式檢查，絕不發起外部驗證請求。"""
    raw_key = (provided_key if provided_key is not None else os.environ.get("CAT1_API_KEY", "")).strip()
    if not raw_key or raw_key in PLACEHOLDER_KEYS:
        return {
            "status": "missing_key",
            "format_valid": False,
            "online_verified": False,
            "plan": "Cat1 Page Monitor (USD 29/month, 7-day free trial, no credit card required)",
            "signup_url": UPGRADE_URL,
            "message": REFERRAL_MESSAGE,
        }

    if not KEY_REGEX.match(raw_key):
        return {
            "status": "invalid_key_format",
            "format_valid": False,
            "online_verified": False,
            "expected_format": "cat1_trial_<16-64 alphanumeric> 或 cat1_live_<16-64 alphanumeric>",
            "signup_url": UPGRADE_URL,
            "message": (
                "提供的金鑰格式不符（預期前綴為 cat1_trial_ 或 cat1_live_ 加 16～64 位英數字元）。\n"
                + REFERRAL_MESSAGE
            ),
        }

    key_tier = "trial" if raw_key.startswith("cat1_trial_") else "live"
    return {
        "status": "format_ok_unverified",
        "format_valid": True,
        "online_verified": False,
        "key_tier_prefix": key_tier,
        "signup_url": UPGRADE_URL,
        "message": (
            "金鑰本地格式檢查相符（注意：本 MCP Server 僅做本地格式檢查，未執行連線驗證，不保證金鑰於遠端已開通或有效）。\n"
            "重要說明：實際 7×24 常駐排程監測由我方自有服務執行，本 MCP Server 不在本地建立背景排程或假裝排程。\n"
            "如需啟用、變更或管理正式排程監測目標，請至 https://toplformater.click 操作。"
        ),
    }


def handle_call_tool(params):
    name = params.get("name")
    args = params.get("arguments") or {}

    if name == "cat1_diff_page":
        target_url = args.get("target_url")
        if not target_url:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "缺少必填參數 target_url"}],
            }
        try:
            diff_res = compare_pages(
                target_source=target_url,
                baseline_source=args.get("baseline_source"),
                baseline_sha256=args.get("baseline_sha256"),
            )
            diff_res["note"] = (
                "此為單頁即時去雜訊比對結果（免費免 Key）。"
                "如需 7×24 常駐排程巡檢與主動告警，請至 https://toplformater.click 申請 7 天免綁卡試用（USD 29／月）。"
            )
            return {
                "isError": False,
                "content": [{"type": "text", "text": json.dumps(diff_res, ensure_ascii=False, indent=2)}],
            }
        except Exception as exc:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"執行去雜訊比對時發生錯誤：{exc}"}],
            }

    if name == "cat1_schedule_monitor":
        target_url = args.get("target_url", "")
        interval = args.get("interval_minutes", 15)
        alert_email = args.get("alert_email", "")
        gate = check_key_gate(args.get("api_key"))
        payload = {
            "tool": "cat1_schedule_monitor",
            "requested_target_url": target_url,
            "requested_interval_minutes": interval,
            "requested_alert_email": alert_email or None,
            "local_scheduler_started": False,
            "gate_result": gate,
        }
        return {
            "isError": False,
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        }

    return {
        "isError": True,
        "content": [{"type": "text", "text": f"未知的工具名稱：{name}"}],
    }


def process_rpc_message(msg):
    """處理單筆 JSON-RPC 2.0 訊息；Notification（無 id）不回傳。"""
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if msg_id is None:
        return None

    if method == "initialize":
        protocol_version = params.get("protocolVersion", "2024-11-05")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        return {"jsonrpc": "2.0", "id": msg_id, "result": handle_call_tool(params)}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
            sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        resp = process_rpc_message(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
