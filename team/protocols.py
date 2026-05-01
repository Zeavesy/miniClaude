"""
Team Protocols — 基于 request_id 关联的结构化握手协议。

两套 FSM:

    Shutdown FSM:
      Lead: shutdown_request(teammate) → 生成 request_id → 发 inbox
      Teammate: 收到 → 决策 → shutdown_response(approve/reject)
      Lead: shutdown_requests[req_id]["status"] → "approved" | "rejected"

    Plan Approval FSM:
      Teammate: plan_approval(plan_text) → 生成 request_id → 发 lead inbox
      Lead: 审查 → plan_approval(request_id, approve, feedback) → 发回
      Teammate: 收到 plan_approval_response → 继续或调整

两个 FSM 共用同一个 request_id 关联模式——
原项目 key insight: "Same request_id correlation pattern, two domains."
"""

import json
import threading
import uuid

# ══════════════════════════════════════════════════════════════
# 请求追踪器 — 全局 dict + Lock 保护并发读写
# ══════════════════════════════════════════════════════════════

shutdown_requests: dict[str, dict] = {}   # {request_id: {target/from, status}}
plan_requests: dict[str, dict] = {}       # {request_id: {from, plan, status}}
_tracker_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════
# Shutdown Protocol — Lead 端
# ══════════════════════════════════════════════════════════════

def handle_shutdown_request(teammate: str, bus) -> str:
    """Lead 向指定队友发送关机请求。"""
    req_id = str(uuid.uuid4())[:8]
    with _tracker_lock:
        shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
    bus.send(
        "lead", teammate, "Please shut down gracefully.",
        "shutdown_request", {"request_id": req_id},
    )
    return f"Shutdown request {req_id} sent to '{teammate}' (status: pending)"


def check_shutdown_status(request_id: str) -> str:
    """Lead 查询关机请求的状态。"""
    with _tracker_lock:
        req = shutdown_requests.get(request_id)
    if not req:
        return f"Error: Unknown request_id '{request_id}'"
    return json.dumps(req, indent=2)


# ══════════════════════════════════════════════════════════════
# Shutdown Protocol — Teammate 端（在 teammate._exec_tool 中调用）
# ══════════════════════════════════════════════════════════════

def handle_shutdown_response(sender: str, request_id: str, approve: bool,
                              reason: str, bus) -> str:
    """Teammate 响应关机请求，更新 tracker 并回发 inbox。"""
    with _tracker_lock:
        if request_id in shutdown_requests:
            shutdown_requests[request_id]["status"] = "approved" if approve else "rejected"
    bus.send(
        sender, "lead", reason,
        "shutdown_response", {"request_id": request_id, "approve": approve},
    )
    return f"Shutdown {'approved' if approve else 'rejected'}"


# ══════════════════════════════════════════════════════════════
# Plan Approval Protocol
# ══════════════════════════════════════════════════════════════

def handle_plan_submit(sender: str, plan_text: str, bus) -> str:
    """Teammate 提交计划等待审批。"""
    req_id = str(uuid.uuid4())[:8]
    with _tracker_lock:
        plan_requests[req_id] = {"from": sender, "plan": plan_text, "status": "pending"}
    bus.send(
        sender, "lead", plan_text, "plan_approval_response",
        {"request_id": req_id, "plan": plan_text},
    )
    return f"Plan submitted (request_id={req_id}). Waiting for lead approval."


def handle_plan_review(request_id: str, approve: bool, feedback: str, bus) -> str:
    """Lead 审查并回复队友的计划。"""
    with _tracker_lock:
        req = plan_requests.get(request_id)
    if not req:
        return f"Error: Unknown plan request_id '{request_id}'"
    with _tracker_lock:
        req["status"] = "approved" if approve else "rejected"
    bus.send(
        "lead", req["from"], feedback, "plan_approval_response",
        {"request_id": request_id, "approve": approve, "feedback": feedback},
    )
    return f"Plan {req['status']} for '{req['from']}'"
