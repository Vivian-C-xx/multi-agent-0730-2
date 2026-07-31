import json
import re
from datetime import datetime

from backend.storage import db_rows, execute


REFLECTION_STEPS = [
    "REFLECTION_INIT",
    "PLAN_REVIEW",
    "WORK_SELF_EVALUATION",
    "WORK_EVIDENCE_FEEDBACK",
    "PROCESS_REVIEW",
    "PROBLEM_IDENTIFICATION",
    "CAUSE_ANALYSIS",
    "IMPROVEMENT_PLAN",
    "STUDENT_CONFIRMATION",
    "REPORT_SAVED",
]

STEP_LABELS = {
    "REFLECTION_INIT": "准备反思",
    "PLAN_REVIEW": "核对计划",
    "WORK_SELF_EVALUATION": "作品自评",
    "WORK_EVIDENCE_FEEDBACK": "查看证据",
    "PROCESS_REVIEW": "回顾过程",
    "PROBLEM_IDENTIFICATION": "选择问题",
    "CAUSE_ANALYSIS": "分析原因",
    "IMPROVEMENT_PLAN": "制定改进",
    "STUDENT_CONFIRMATION": "确认报告",
    "REPORT_SAVED": "报告已保存",
}

DEFAULT_RUBRIC = [
    {"dimension": "运行效果", "criteria": "程序能运行，输出结果和题目要求基本一致。"},
    {"dimension": "功能实现", "criteria": "主要功能完整，输入、处理、输出关系清楚。"},
    {"dimension": "代码规范", "criteria": "变量名较清楚，缩进正确，代码结构容易阅读。"},
]

VAGUE_ACTION_WORDS = ["认真一点", "多练习", "多检查", "仔细一点", "努力一点", "好好学"]


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def unavailable(reason="当前记录中暂时没有这项数据。"):
    return {"available": False, "reason": reason}


def available(value):
    return {"available": True, "value": value}


def safe_json_loads(value, default=None):
    if default is None:
        default = {}
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def student_id_from_state(state):
    return state.setdefault("student_session_id", "")


def ensure_learning_run(state):
    session_id = student_id_from_state(state)
    run_id = state.get("learning_run_id")
    if run_id:
        rows = db_rows("SELECT * FROM learning_runs WHERE id = ? AND session_id = ?", (run_id, session_id))
        if rows and rows[0].get("status") == "active":
            update_learning_run_from_state(rows[0]["id"], state)
            return rows[0]

    rows = db_rows(
        """
        SELECT * FROM learning_runs
        WHERE session_id = ? AND status = 'active'
        ORDER BY id DESC LIMIT 1
        """,
        (session_id,),
    )
    if rows:
        state["learning_run_id"] = rows[0]["id"]
        update_learning_run_from_state(rows[0]["id"], state)
        return rows[0]

    timestamp = now_text()
    previous_report = latest_reflection_report(session_id)
    if previous_report:
        state["previous_improvement_actions"] = previous_report.get("improvementActions", [])
    execute(
        """
        INSERT INTO learning_runs
        (session_id, student_name, topic, exercise_prompt, status, current_phase,
         previous_reflection_report_id, started_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            state.get("student_name", ""),
            state.get("current_topic", ""),
            state.get("exercise_prompt", ""),
            state.get("learning_phase", ""),
            previous_report.get("id") if previous_report else None,
            timestamp,
            timestamp,
            timestamp,
        ),
    )
    row = db_rows(
        "SELECT * FROM learning_runs WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    )[0]
    state["learning_run_id"] = row["id"]
    return row


def update_learning_run_from_state(run_id, state):
    execute(
        """
        UPDATE learning_runs
        SET student_name = ?, topic = ?, exercise_prompt = ?, current_phase = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            state.get("student_name", ""),
            state.get("current_topic", ""),
            state.get("exercise_prompt", ""),
            state.get("learning_phase", ""),
            now_text(),
            run_id,
        ),
    )


def latest_reflection_report(student_id):
    rows = db_rows(
        """
        SELECT * FROM reflection_reports
        WHERE student_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (student_id,),
    )
    if not rows:
        return None
    row = rows[0]
    row["report"] = safe_json_loads(row.get("report_json"), {})
    row["improvementActions"] = safe_json_loads(row.get("improvement_actions"), [])
    return row


def task_completion_index(step):
    mapping = {
        "topic_intro": 0,
        "experience_feedback": 0,
        "life_connection": 0,
        "exercise_intake": 0,
        "quiz": 0,
        "quiz_review": 0,
        "plan_allocation": 0,
        "ipo_analysis": 0,
        "flowchart": 1,
        "debugging": 2,
        "self_evaluation": 4,
    }
    return mapping.get(step, 0)


def task_reviews_from_plan(plan, step, progress=None):
    planned = plan or []
    completed_count = task_completion_index(step)
    if progress == 100:
        completed_count = len(planned)
    reviews = []
    for index, task in enumerate(planned):
        reviews.append(
            {
                "name": task.get("name", ""),
                "plannedMinutes": int(task.get("minutes", 0) or 0),
                "completed": index < completed_count,
                "actualMinutes": None,
                "timeDeviationMinutes": None,
                "actualStatus": unavailable("当前版本只记录了计划时间，未记录每项任务的真实耗时。"),
            }
        )
    return reviews


def extract_submitted_code(interactions):
    code_blocks = []
    for row in interactions:
        text = row.get("user_message", "")
        blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.S | re.I)
        code_blocks.extend(block.strip() for block in blocks if block.strip())
        if not blocks and any(token in text for token in ["print(", "input(", "def ", "for ", "if "]):
            code_blocks.append(text.strip())
    if not code_blocks:
        return unavailable("当前聊天记录中没有发现学生提交的完整代码。")
    return available(code_blocks[-1])


def infer_run_results(interactions):
    success_words = ["运行成功", "调试成功", "没有报错", "无报错", "问题解决"]
    error_words = ["Traceback", "SyntaxError", "TypeError", "NameError", "报错", "运行错误"]
    for row in reversed(interactions):
        text = row.get("user_message", "")
        if any(word in text for word in success_words):
            return available({"status": "success", "source": "student_message", "message": text[:300]})
        if any(word in text for word in error_words):
            return available({"status": "error", "source": "student_message", "message": text[:300]})
    return unavailable("当前记录中没有结构化程序运行结果。")


def static_code_checks(submitted_code):
    if not submitted_code.get("available"):
        return unavailable("没有可检查的代码。")
    code = submitted_code["value"]
    checks = []
    checks.append({"name": "包含输出语句", "passed": "print(" in code})
    checks.append({"name": "缩进看起来完整", "passed": "\t" not in code})
    checks.append({"name": "代码不为空", "passed": bool(code.strip())})
    return available(checks)


def count_debug_interactions(interactions, state):
    count = int(state.get("debug_count", 0) or 0)
    if count:
        return count
    debug_words = ["调试", "报错", "错误", "bug", "Traceback", "SyntaxError", "TypeError", "NameError"]
    return sum(1 for row in interactions if row.get("agent") == "mentor" and any(word in row.get("user_message", "") for word in debug_words))


def interactions_by_agent(interactions, agent):
    return [
        {
            "createdAt": row.get("created_at"),
            "phase": row.get("phase"),
            "studentMessage": row.get("user_message", "")[:300],
            "agentMessage": row.get("assistant_message", "")[:300],
        }
        for row in interactions
        if row.get("agent") == agent
    ]


def assemble_reflection_context(state, learning_session_id=None):
    run = ensure_learning_run(state)
    session_id = learning_session_id or student_id_from_state(state)
    if session_id != student_id_from_state(state):
        raise PermissionError("不能读取其他学习会话的反思数据。")

    interactions = db_rows(
        "SELECT * FROM interactions WHERE session_id = ? ORDER BY created_at ASC, id ASC",
        (session_id,),
    )
    plan = state.get("time_plan") or []
    debug_count = count_debug_interactions(interactions, state)
    submitted_code = extract_submitted_code(interactions)
    run_results = infer_run_results(interactions)
    test_results = unavailable("当前项目还没有教师测试用例或安全代码执行沙箱。")
    code_checks = static_code_checks(submitted_code)
    previous = latest_reflection_report(student_id_from_state(state))

    context = {
        "learningRunId": run["id"],
        "learningSessionId": session_id,
        "studentId": student_id_from_state(state),
        "learningGoal": available(state.get("exercise_prompt") or state.get("current_topic")) if (state.get("exercise_prompt") or state.get("current_topic")) else unavailable("学生还没有形成明确的练习题干。"),
        "plannedTasks": available(task_reviews_from_plan(plan, state.get("learning_step", ""), state.get("progress"))) if plan else unavailable("当前记录中没有完整学习计划。"),
        "plannedDurations": available(plan) if plan else unavailable("当前记录中没有计划时间。"),
        "actualTaskRecords": unavailable("当前版本没有逐项任务完成时间的结构化记录。"),
        "actualDurations": unavailable("当前版本没有真实耗时的结构化记录。"),
        "submittedCode": submitted_code,
        "codeVersions": unavailable("当前版本没有程序版本历史。"),
        "runResults": run_results,
        "testResults": test_results,
        "staticCodeChecks": code_checks,
        "debugCount": available(debug_count),
        "mentorInteractions": interactions_by_agent(interactions, "mentor"),
        "peerInteractions": interactions_by_agent(interactions, "peer"),
        "assistantInteractions": interactions_by_agent(interactions, "assistant"),
        "progressEvents": progress_events_from_interactions(interactions),
        "previousReflection": previous["report"] if previous else unavailable("还没有上一轮正式反思报告。"),
        "rubric": DEFAULT_RUBRIC,
    }
    context["taskReview"] = build_task_review(context)
    context["workEvidence"] = build_work_evidence(context)
    context["processSummary"] = build_process_summary(context)
    context["problemCues"] = build_problem_cues(context)
    return context


def progress_events_from_interactions(interactions):
    events = []
    for row in interactions:
        metadata = safe_json_loads(row.get("metadata"), {})
        if metadata.get("learning_step") or metadata.get("start_timer") or metadata.get("complete_timer") or metadata.get("overtime"):
            events.append(
                {
                    "createdAt": row.get("created_at"),
                    "phase": row.get("phase"),
                    "agent": row.get("agent"),
                    "event": metadata,
                }
            )
    return events


def build_task_review(context):
    planned = context.get("plannedTasks", {})
    items = planned.get("value", []) if planned.get("available") else []
    total_planned = sum(item.get("plannedMinutes", 0) for item in items)
    completed = [item for item in items if item.get("completed")]
    return {
        "plannedTasks": items,
        "completedTasks": completed,
        "plannedDuration": total_planned if items else None,
        "actualDuration": None,
        "timeDeviations": [
            {
                "taskName": item.get("name"),
                "plannedMinutes": item.get("plannedMinutes"),
                "actualMinutes": item.get("actualMinutes"),
                "deviationMinutes": item.get("timeDeviationMinutes"),
                "status": "实际耗时暂无记录",
            }
            for item in items
        ],
        "studentGoalJudgement": None,
    }


def build_work_evidence(context):
    return {
        "rubric": DEFAULT_RUBRIC,
        "objectiveEvidence": {
            "runResults": context.get("runResults"),
            "testResults": context.get("testResults"),
            "staticCodeChecks": context.get("staticCodeChecks"),
        },
        "agentExplanation": "当前只展示可查到的客观证据。没有运行结果或测试用例时，系统不会猜测程序是否正确。",
    }


def build_process_summary(context):
    task_review = context.get("taskReview", {})
    return {
        "taskCompletion": task_review.get("plannedTasks", []),
        "timeUse": "计划时间已记录；真实耗时暂无结构化记录。",
        "debugCount": context.get("debugCount", {}).get("value", 0),
        "keyHelpRecords": {
            "mentor": context.get("mentorInteractions", [])[-3:],
            "peer": context.get("peerInteractions", [])[-3:],
            "assistant": context.get("assistantInteractions", [])[-3:],
        },
        "importantEvents": context.get("progressEvents", [])[-8:],
    }


def build_problem_cues(context):
    cues = []
    task_review = context.get("taskReview", {})
    planned_tasks = task_review.get("plannedTasks", [])
    if planned_tasks and len(task_review.get("completedTasks", [])) < len(planned_tasks):
        cues.append(
            {
                "description": "有计划任务可能还没有全部完成。",
                "evidence": "任务完成记录显示还有未完成项。",
                "source": "系统数据",
                "studentConfirmed": False,
            }
        )
    if context.get("debugCount", {}).get("value", 0) >= 2:
        cues.append(
            {
                "description": "调试次数较多，可能需要回顾调试方法。",
                "evidence": f"本轮记录到 {context['debugCount']['value']} 次调试相关求助。",
                "source": "系统数据",
                "studentConfirmed": False,
            }
        )
    if not context.get("runResults", {}).get("available"):
        cues.append(
            {
                "description": "程序运行结果没有被完整记录。",
                "evidence": context.get("runResults", {}).get("reason", "缺少运行结果。"),
                "source": "系统数据",
                "studentConfirmed": False,
            }
        )
    if not cues:
        cues.append(
            {
                "description": "当前记录没有发现明显异常，可以请你自己补充一个最想改进的地方。",
                "evidence": "系统没有检测到超时、反复调试或未完成等明确现象。",
                "source": "系统数据",
                "studentConfirmed": False,
            }
        )
    return cues


def get_or_create_reflection_session(state):
    run = ensure_learning_run(state)
    student_id = student_id_from_state(state)
    rows = db_rows(
        """
        SELECT * FROM reflection_sessions
        WHERE learning_session_id = ? AND status != 'completed'
        ORDER BY id DESC LIMIT 1
        """,
        (student_id,),
    )
    if rows:
        return rows[0], False
    timestamp = now_text()
    execute(
        """
        INSERT INTO reflection_sessions
        (student_id, learning_session_id, learning_run_id, task_id, current_step, status,
         started_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (
            student_id,
            student_id,
            run["id"],
            state.get("exercise_prompt", "")[:80],
            "PLAN_REVIEW",
            timestamp,
            timestamp,
            timestamp,
        ),
    )
    session = db_rows(
        "SELECT * FROM reflection_sessions WHERE learning_session_id = ? ORDER BY id DESC LIMIT 1",
        (student_id,),
    )[0]
    return session, True


def reflection_step_payload(reflection_session_id, step):
    rows = db_rows(
        "SELECT payload FROM reflection_step_data WHERE reflection_session_id = ? AND step = ?",
        (reflection_session_id, step),
    )
    if not rows:
        return {}
    return safe_json_loads(rows[0].get("payload"), {})


def all_reflection_step_data(reflection_session_id):
    rows = db_rows(
        "SELECT step, payload FROM reflection_step_data WHERE reflection_session_id = ?",
        (reflection_session_id,),
    )
    return {row["step"]: safe_json_loads(row.get("payload"), {}) for row in rows}


def save_reflection_step(state, step, payload, next_step=None):
    if step not in REFLECTION_STEPS:
        raise ValueError("未知的反思步骤。")
    session, _ = get_or_create_reflection_session(state)
    timestamp = now_text()
    execute(
        """
        INSERT INTO reflection_step_data
        (reflection_session_id, step, payload, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(reflection_session_id, step)
        DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
        """,
        (
            session["id"],
            step,
            json.dumps(payload or {}, ensure_ascii=False),
            timestamp,
            timestamp,
        ),
    )
    target_step = next_step or next_reflection_step(step)
    if target_step:
        set_reflection_step(session["id"], target_step)
    return get_reflection_session_payload(state)


def next_reflection_step(step):
    try:
        index = REFLECTION_STEPS.index(step)
    except ValueError:
        return None
    if index + 1 >= len(REFLECTION_STEPS):
        return step
    return REFLECTION_STEPS[index + 1]


def previous_reflection_step(step):
    try:
        index = REFLECTION_STEPS.index(step)
    except ValueError:
        return None
    return REFLECTION_STEPS[max(1, index - 1)]


def set_reflection_step(reflection_session_id, step):
    execute(
        "UPDATE reflection_sessions SET current_step = ?, updated_at = ? WHERE id = ?",
        (step, now_text(), reflection_session_id),
    )


def get_reflection_session_payload(state):
    session, created = get_or_create_reflection_session(state)
    context = assemble_reflection_context(state, session["learning_session_id"])
    state["reflection_current_step"] = session["current_step"]
    return {
        "session": session,
        "created": created,
        "steps": REFLECTION_STEPS,
        "stepLabels": STEP_LABELS,
        "currentStep": session["current_step"],
        "context": context,
        "draft": all_reflection_step_data(session["id"]),
    }


def validate_improvement_action(action):
    missing = []
    for field in ["relatedProblem", "action", "verification", "nextUseContext"]:
        if not str(action.get(field, "")).strip():
            missing.append(field)
    text = str(action.get("action", "")).strip()
    vague = any(word in text for word in VAGUE_ACTION_WORDS) or len(text) < 8
    return {
        "ok": not missing and not vague,
        "missingFields": missing,
        "needsDetail": vague,
        "message": "请把改进措施写得更具体。" if vague else "",
    }


def validate_improvement_actions(actions):
    results = [validate_improvement_action(action) for action in (actions or [])]
    return {"ok": bool(results) and all(item["ok"] for item in results), "items": results}


def build_report_from_draft(state):
    session, _ = get_or_create_reflection_session(state)
    draft = all_reflection_step_data(session["id"])
    context = assemble_reflection_context(state, session["learning_session_id"])
    plan_review = draft.get("PLAN_REVIEW", {})
    work_self = draft.get("WORK_SELF_EVALUATION", {})
    work_final = draft.get("WORK_EVIDENCE_FEEDBACK", {})
    process_review = draft.get("PROCESS_REVIEW", {})
    problems = draft.get("PROBLEM_IDENTIFICATION", {})
    causes = draft.get("CAUSE_ANALYSIS", {})
    improvements = draft.get("IMPROVEMENT_PLAN", {})
    return {
        "goalAchievement": plan_review.get("studentGoalJudgement"),
        "workEvaluation": {
            "rubric": DEFAULT_RUBRIC,
            "studentSelfEvaluation": work_self,
            "objectiveEvidence": context.get("workEvidence", {}).get("objectiveEvidence"),
            "agentExplanation": context.get("workEvidence", {}).get("agentExplanation"),
            "studentFinalEvaluation": work_final.get("studentFinalEvaluation"),
        },
        "learningStrengths": process_review.get("learningStrengths", []),
        "mainProblems": problems.get("confirmedProblems", []),
        "causeAnalysis": causes.get("confirmedCauses", []),
        "effectiveExperiences": process_review.get("effectiveExperiences", []),
        "improvementActions": improvements.get("actions", []),
        "systemData": {
            "taskReview": context.get("taskReview"),
            "processSummary": context.get("processSummary"),
        },
        "agentSuggestions": {
            "problemCues": context.get("problemCues"),
            "workEvidence": context.get("workEvidence"),
        },
    }


def save_final_report(state, confirmation_payload):
    session, _ = get_or_create_reflection_session(state)
    report = build_report_from_draft(state)
    report["studentConfirmation"] = confirmation_payload or {}
    report["studentConfirmedAt"] = now_text()
    improvements = report.get("improvementActions") or []
    validation = validate_improvement_actions(improvements)
    if not validation["ok"]:
        raise ValueError("改进措施还不够完整，请先补充具体行动和判断标准。")
    timestamp = now_text()
    execute(
        """
        INSERT INTO reflection_reports
        (reflection_session_id, student_id, learning_session_id, learning_run_id, objective_data,
         agent_suggestions, student_confirmed_content, improvement_actions, report_json,
         student_confirmed_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session["id"],
            student_id_from_state(state),
            session["learning_session_id"],
            session.get("learning_run_id"),
            json.dumps(report.get("systemData", {}), ensure_ascii=False),
            json.dumps(report.get("agentSuggestions", {}), ensure_ascii=False),
            json.dumps(confirmation_payload or {}, ensure_ascii=False),
            json.dumps(improvements, ensure_ascii=False),
            json.dumps(report, ensure_ascii=False),
            report["studentConfirmedAt"],
            timestamp,
        ),
    )
    report_id = db_rows(
        "SELECT id FROM reflection_reports WHERE reflection_session_id = ? ORDER BY id DESC LIMIT 1",
        (session["id"],),
    )[0]["id"]
    for action in improvements:
        execute(
            """
            INSERT INTO reflection_improvement_actions
            (reflection_report_id, student_id, related_problem, related_cause, action,
             verification, next_use_context, student_confirmed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                report_id,
                student_id_from_state(state),
                action.get("relatedProblem", ""),
                action.get("relatedCause", ""),
                action.get("action", ""),
                action.get("verification", ""),
                action.get("nextUseContext", ""),
                timestamp,
            ),
        )
    execute(
        """
        UPDATE reflection_sessions
        SET current_step = 'REPORT_SAVED', status = 'completed', completed_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (timestamp, timestamp, session["id"]),
    )
    execute(
        "UPDATE learning_runs SET status = 'reflected', completed_at = ?, updated_at = ? WHERE id = ?",
        (timestamp, timestamp, session.get("learning_run_id")),
    )
    state["last_reflection_report_id"] = report_id
    state["previous_improvement_actions"] = improvements
    state["reflection_current_step"] = "REPORT_SAVED"
    state["learning_run_id"] = None
    return {"reportId": report_id, "report": report}
