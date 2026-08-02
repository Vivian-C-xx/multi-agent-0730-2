import re

from backend.services.llm_client import call_llm
from backend.utils import contains_any

TASK_PATTERNS = [
    ("分析问题", ["分析问题", "问题分析", "需求分析", "分析"]),
    ("设计算法", ["设计算法", "算法设计", "设计程序", "程序设计", "设计步骤", "设计思路", "算法"]),
    ("编写程序", ["编写程序", "程序编写", "代码编写", "写代码", "写程序", "编程"]),
    ("代码优化", ["代码优化", "优化代码", "优化程序", "程序优化", "优化"]),
]
TASK_NAMES = [name for name, _ in TASK_PATTERNS]

REPLAN_WORDS = ["重新分配", "调整时间", "剩余时间", "再分配", "重置时间"]
DEBUG_SUCCESS_WORDS = [
    "调试成功",
    "运行成功",
    "成功运行",
    "成功运行了",
    "可以运行了",
    "能运行了",
    "可以正常运行",
    "能正常运行",
    "跑通",
    "跑通了",
    "没有报错",
    "无报错",
    "代码成功",
    "问题解决",
]
DEBUG_FAILURE_WORDS = [
    "不能运行",
    "无法运行",
    "不会运行",
    "没法运行",
    "运行不了",
    "跑不通",
    "不能执行",
    "无法执行",
    "还是不能运行",
    "还不能运行",
    "仍然不能运行",
    "没有成功运行",
    "没成功运行",
    "没有跑通",
    "还是报错",
    "仍然报错",
    "报错",
    "错误",
    "bug",
    "Bug",
    "BUG",
    "Traceback",
    "SyntaxError",
    "TypeError",
    "NameError",
]
CODE_HELP_WORDS = [
    "修改代码",
    "改代码",
    "优化代码",
    "调试代码",
    "代码怎么改",
    "哪里错",
    "哪错",
    "为什么错",
    "运行错误",
    "运行结果",
    "运行不了",
    "不能运行",
]
FLOWCHART_COMPLETION_WORDS = [
    "流程图框架补全完成",
    "流程图完成",
    "流程图正确",
    "所有空白都填对",
    "所有空白都对",
    "进入第五步",
    "开始第五步",
    "进入第三步任务",
    "开始第三步任务",
    "进入代码编写",
    "开始代码编写",
]
REFLECTION_WORDS = ["学习完", "学完", "本节课结束", "完成相关内容", "请生成报告", "自评", "反思", "学习评价"]
LLM_ERROR_MARKERS = [
    "还没有配置 DeepSeek API 密钥",
    "大模型 API",
    "暂时无法连接大模型",
    "连接大模型 API",
    "调用大模型 API",
    "大模型返回了空内容",
]

AGENT_LABELS = "编程自主学习管家|编程助教智能体|编程导师智能体|编程同伴智能体"
AGENT_LABEL_RE = re.compile(
    rf"(?:^|\n)\s*(?:[【\[]\s*(?:{AGENT_LABELS})\s*[】\]]\s*[:：]?|(?:{AGENT_LABELS})\s*[:：])\s*"
)


def strip_agent_labels(message):
    cleaned = message or ""
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = AGENT_LABEL_RE.sub("\n", cleaned)
    return cleaned.strip()


def soften_reply_format(message):
    parts = re.split(r"(```.*?```)", message or "", flags=re.S)
    cleaned_parts = []
    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            cleaned_parts.append(part)
            continue
        part = re.sub(r"(?m)^\s*[-*_]{3,}\s*$\n?", "", part)
        part = re.sub(r"(?m)^\s*#{1,6}\s*", "", part)
        part = re.sub(r"(?m)^\s*[*+-]\s+", "", part)
        part = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", part)
        part = re.sub(r"(?m)^\s*>\s*", "", part)
        cleaned_parts.append(part)
    return "".join(cleaned_parts).strip()


def clean_reply(message):
    cleaned = soften_reply_format(strip_agent_labels(message))
    cleaned = replace_unavailable_ui_references(cleaned)
    return normalize_student_task_step_labels(cleaned)


def normalize_student_task_step_labels(message):
    if not message:
        return message
    text = message
    replacements = [
        (r"当前是第三步[：:]?请用IPO模式", "当前是第一步任务“分析问题”：请用IPO模式"),
        (r"当前是第三步[：:]?", "当前是第一步任务“分析问题”："),
        (r"开始第四步[：:]?\s*(?:生成流程图框架|设计流程图|设计算法)", "开始第二步任务“设计算法”"),
        (r"进入第四步[：:]?\s*(?:生成流程图框架|设计流程图|设计算法)", "进入第二步任务“设计算法”"),
        (r"第四步[：:]?\s*(?:流程图框架补全|流程图|设计算法)", "第二步任务“设计算法”"),
        (r"第四步流程图框架", "第二步任务“设计算法”流程图框架"),
        (r"第四步", "第二步任务“设计算法”"),
        (r"开始第五步[：:]?\s*(?:编写代码|编写程序|代码编写|编程)", "开始第三步任务“编写程序”"),
        (r"进入第五步[：:]?\s*(?:编写代码|编写程序|代码编写|编程)", "进入第三步任务“编写程序”"),
        (r"第五步[：:]?\s*(?:编写代码|编写程序|代码编写|编程|编写程序与调试)", "第三步任务“编写程序”"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def looks_like_numbered_flowchart_answer(message):
    text = message or ""
    numbered = set(re.findall(r"(?:___\s*)?([1-9])(?:\s*___)?\s*[：:=、.)）]", text))
    if len(numbered) >= 3:
        return True
    compact = re.sub(r"\s+", "", text)
    return bool(re.search(r"___?1___?.+___?2___?.+___?3___?", compact))


def mentor_claims_flowchart_complete(message):
    return contains_any(message or "", FLOWCHART_COMPLETION_WORDS)


def looks_like_programming_ready(message):
    return contains_any(message or "", ["准备好了", "开始写", "开始编程", "可以写", "进入编写", "写代码"])


def looks_like_flowchart_diagram(message):
    text = message or ""
    return "挖空流程图" in text and bool(re.search(r"（(?:圆角矩形|平行四边形|矩形|菱形)）", text))


def looks_like_code_blank_algorithm(message):
    text = message or ""
    if contains_any(text, ["Python代码", "代码填空", "input()", "float(", "print("]):
        return True
    return bool(re.search(r"(?m)^\s*[A-Za-z_]\w*\s*=\s*[_＿—-]{3,}", text))


def algorithm_flowchart_prompt_message(state):
    exercise = state.get("exercise_prompt") or "当前练习任务"
    if contains_any(exercise, ["BMI", "bmi", "身高", "体重"]):
        nodes = (
            "（圆角矩形）开始\n"
            "↓\n"
            "（平行四边形）输入 ___1___、___2___\n"
            "↓\n"
            "（矩形）计算：BMI = ___3___\n"
            "↓\n"
            "（平行四边形）输出 ___4___\n"
            "↓\n"
            "（圆角矩形）结束"
        )
        blanks = "___1___、___2___、___3___、___4___"
    else:
        nodes = (
            "（圆角矩形）开始\n"
            "↓\n"
            "（平行四边形）输入 ___1___\n"
            "↓\n"
            "（矩形）处理：___2___\n"
            "↓\n"
            "（平行四边形）输出 ___3___\n"
            "↓\n"
            "（圆角矩形）结束"
        )
        blanks = "___1___、___2___、___3___"
    return (
        "现在进入第二步任务“设计算法”。这一步只设计流程图，不写代码。\n\n"
        "请根据刚才的IPO分析，补全下面流程图节点里的空白。\n\n"
        f"练习任务：{exercise}\n\n"
        f"挖空流程图：\n{nodes}\n\n"
        f"请回答：{blanks}分别应该填什么？"
    )


def guard_algorithm_design_flowchart_format(state, agent, assistant_message):
    if state.get("learning_step") != "flowchart" or agent != "mentor":
        return assistant_message
    if looks_like_flowchart_diagram(assistant_message):
        return assistant_message
    if looks_like_code_blank_algorithm(assistant_message):
        return algorithm_flowchart_prompt_message(state)
    return assistant_message


def guard_premature_flowchart_completion(state, agent, user_message, assistant_message):
    if state.get("learning_step") != "flowchart" or agent != "mentor":
        return assistant_message
    if not mentor_claims_flowchart_complete(assistant_message):
        return assistant_message
    if looks_like_numbered_flowchart_answer(user_message):
        return assistant_message
    return (
        "我先不判断流程图已经完成，因为你还没有按空白编号逐项填写。\n\n"
        "请你按这个格式回答：\n"
        "___1___：\n"
        "___2___：\n"
        "___3___：\n"
        "___4___：\n\n"
        "如果你想写完整流程，也可以写，但需要把每个空白编号对应的答案标出来。"
    )


def programming_prompt_message(state):
    exercise = state.get("exercise_prompt") or "当前练习任务"
    return (
        f"现在进入编写程序任务。你的练习任务是：{exercise}\n\n"
        "请你根据刚才完成的IPO分析和流程图，自己写出完整 Python 程序。\n\n"
        "写代码前可以简单检查这几件事：\n"
        "1. 输入：需要从用户那里得到哪些数据？\n"
        "2. 处理：核心公式或判断条件是什么？\n"
        "3. 输出：最后要显示什么结果？\n\n"
        "请直接编写完整代码并运行。运行后把代码和运行结果发给我；如果报错，我再帮你一起调试。"
    )


def guard_programming_stage_overguidance(state, agent, user_message, assistant_message):
    if state.get("learning_step") != "debugging" or agent != "mentor":
        return assistant_message
    if contains_any(user_message or "", ["报错", "错误", "bug", "Traceback", "SyntaxError", "TypeError", "NameError"]):
        return assistant_message
    if looks_like_programming_ready(user_message):
        return programming_prompt_message(state)
    return assistant_message


def replace_unavailable_ui_references(message):
    if not message:
        return message
    text = message
    replacements = [
        (r"学习报告已保存[，,。；;]?\s*后续可在教师端学习数据中查看或导出[。！!]*", "学习报告已保存。"),
        (r"学习报告已保存[，,。；;]?\s*后续可在教师端导出的学习数据中查看记录[。！!]*", "学习报告已保存。"),
        (r"学习报告已保存[，,。；;]?\s*(?:可|可以|后续可)?.*?(?:我的反思报告|个人中心|学习中心|教师端学习数据|教师端导出的学习数据).*?(?:查看|导出|记录)?[。！!]*", "学习报告已保存。"),
        (r"你可以?至?个人中心查看历史记录", "学习报告已保存。"),
        (r"你可以?到学习中心查看历史记录", "学习报告已保存。"),
        (r"可至个人中心查看历史记录", "学习报告已保存。"),
        (r"可到学习中心查看历史记录", "学习报告已保存。"),
        (r"后续可在教师端学习数据中查看或导出", "学习报告已保存。"),
        (r"后续可在教师端导出的学习数据中查看记录", "学习报告已保存。"),
        (r"可在学生端右侧的“我的反思报告”中查看", ""),
        (r"学生端右侧的“我的反思报告”", "学习报告"),
        (r"我的反思报告", "学习报告"),
        (r"教师端学习数据", "学习报告"),
        (r"教师端导出的学习数据", "学习报告"),
        (r"个人中心", "学习报告"),
        (r"学习中心", "学习报告"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text

def format_quiz_layout(message):
    if not message:
        return message
    parts = re.split(r"(```.*?```)", message, flags=re.S)
    formatted_parts = []
    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            formatted_parts.append(part)
            continue
        text = part
        text = re.sub(r"(?<!^)(?<!\n)\s*(题目\s*\d+(?:\s*[（(]|[.．、])?)", r"\n\n\1", text)
        text = re.sub(r"(?<!^)(?<!\n)\s*(\d+\s*[.．、]\s*)", r"\n\n\1", text)
        text = re.sub(r"(题目\s*\d+\s*[（(][^）)]{1,10}[）)])\s*(?=\S)", r"\1\n", text)
        text = re.sub(r"(?<!\n)\s*([A-D][.．、)）])\s*", r"\n\1 ", text)
        text = re.sub(r"(?<!\n)(（回答[“\"']?对[”\"']?或[“\"']?错[”\"']?）)", r"\n\1", text)
        text = re.sub(r"\n(题目\s*\d+\s*[（(][^）)]{1,10}[）)])\n+", r"\n\n\1\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        formatted_parts.append(text)
    formatted = "".join(formatted_parts).strip()
    formatted = re.sub(r"(?m)^\s*题目\s*(\d+)\s*[（(]\s*(?:单选|判断)\s*[）)]\s*", r"\1. ", formatted)
    formatted = re.sub(r"(?m)^(\d+\.\s*[^\n]+)\n(?=[A-D][.．、)）])", r"\1\n\n", formatted)
    formatted = re.sub(r"(?m)^(\d+\.\s*[^\n]+)\n(?=（回答)", r"\1\n\n", formatted)
    formatted = re.sub(r"(?m)^([A-D][.．、)）]\s*[^\n]+)\n(?=[A-D][.．、)）])", r"\1\n\n", formatted)
    formatted = re.sub(r"(?m)^([A-D][.．、)）]\s*[^\n]+)\n(?=\d+\.\s*)", r"\1\n\n", formatted)
    formatted = re.sub(r"\n{4,}", "\n\n", formatted)
    return formatted.strip()

def should_format_quiz(agent, step):
    return agent == "assistant" and step in {"exercise_intake", "quiz_review"}


def split_quiz_blocks(message):
    formatted = format_quiz_layout(message)
    blocks = []
    current = []
    for line in formatted.splitlines():
        if re.match(r"^\s*(?:题目\s*)?\d+\s*[.．、]", line) and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        block = "\n".join(current).strip()
        if re.search(r"(?:题目\s*)?\d+\s*[.．、]", block):
            blocks.append(block)
    return blocks


def quiz_layout_issues(message):
    issues = []
    for block in split_quiz_blocks(message):
        title = block.splitlines()[0].strip()
        if "```" in block:
            issues.append({"question": title, "codeBlock": True})
            continue
        if "判断" in title or "回答" in block:
            continue
        options = set(re.findall(r"(?m)^\s*([A-D])[\.\．、\)）]", block))
        missing = [option for option in "ABCD" if option not in options]
        if missing:
            issues.append({"question": title, "missingOptions": missing})
    return issues


def quiz_layout_is_complete(message):
    blocks = split_quiz_blocks(message)
    return bool(blocks) and not quiz_layout_issues(message)


def looks_like_llm_error(message):
    return contains_any(message or "", LLM_ERROR_MARKERS)


def fallback_quiz_message(state):
    exercise = state.get("exercise_prompt") or state.get("current_topic") or "当前编程任务"
    is_bmi = contains_any(exercise, ["BMI", "bmi", "身高", "体重"])
    if is_bmi:
        return (
            "我先给你一组格式完整的基础知识前测。请按顺序作答，例如：1A 2C 3对。\n\n"
            "1. 在计算BMI的程序中，input() 的主要作用是（）\n\n"
            "A. 接收用户输入\n\n"
            "B. 自动计算BMI\n\n"
            "C. 结束程序\n\n"
            "D. 删除变量\n\n"
            "2. 如果身高变量是 height，体重变量是 weight，计算BMI的表达式应是（）\n\n"
            "A. height / (weight * weight)\n\n"
            "B. weight / (height * height)\n\n"
            "C. height + weight\n\n"
            "D. weight * height\n\n"
            "3. 在 Python 中，float(input()) 可以把用户输入的内容转换成小数。\n\n"
            "（回答“对”或“错”）"
        )
    return (
        "我先给你一组格式完整的基础知识前测。请按顺序作答，例如：1A 2B 3对。\n\n"
        "1. 程序顺序结构最主要的特点是（）\n\n"
        "A. 根据条件选择性运行代码\n\n"
        "B. 按照代码书写顺序，从上到下依次执行\n\n"
        "C. 重复执行一段代码\n\n"
        "D. 代码执行顺序可以自动跳跃\n\n"
        "2. 在 Python 中，变量的主要作用是（）\n\n"
        "A. 保存数据\n\n"
        "B. 改变电脑屏幕颜色\n\n"
        "C. 自动生成图片\n\n"
        "D. 删除程序\n\n"
        "3. input() 通常用来接收用户输入。\n\n"
        "（回答“对”或“错”）"
    )


def quiz_regeneration_prompt(original_message):
    return (
        "刚才生成的基础知识测试题格式不完整，不能直接给学生作答。"
        "请重新生成一组3-5道基础知识测试题，只输出题目，不要解释原因。"
        "必须严格遵守：每道题用“1. 题干（）”这种数字编号开头；"
        "如果是单选题，必须有且只有A、B、C、D四个选项，并且每个选项独立成行；"
        "如果是判断题，题干下一行写“（回答“对”或“错”）”。"
        "题目和每个选项之间都空一行，像教材练习题一样清楚。"
        "不要把题干和选项挤在同一行，不要缺少任何单选题选项。\n\n"
        f"原始不完整输出如下：\n{original_message}"
    )


def ensure_complete_quiz_message(state, agent, step, message):
    formatted = format_quiz_layout(message)
    if not should_format_quiz(agent, step):
        return formatted, {"quiz_layout_checked": False}
    if looks_like_llm_error(formatted):
        return formatted, {
            "quiz_layout_checked": True,
            "quiz_layout_complete": False,
            "quiz_llm_error": True,
        }
    issues = quiz_layout_issues(formatted)
    if not issues and split_quiz_blocks(formatted):
        return formatted, {"quiz_layout_checked": True, "quiz_layout_complete": True}
    retry = call_llm(state, agent, quiz_regeneration_prompt(formatted))
    retry = format_quiz_layout(clean_reply(retry))
    if looks_like_llm_error(retry):
        return retry, {
            "quiz_layout_checked": True,
            "quiz_layout_complete": False,
            "quiz_regenerated": True,
            "quiz_llm_error": True,
            "quiz_layout_issues": issues,
        }
    retry_issues = quiz_layout_issues(retry)
    if not retry_issues and split_quiz_blocks(retry):
        return retry, {
            "quiz_layout_checked": True,
            "quiz_layout_complete": True,
            "quiz_regenerated": True,
            "quiz_layout_issues": issues,
        }
    fallback = format_quiz_layout(fallback_quiz_message(state))
    return fallback, {
        "quiz_layout_checked": True,
        "quiz_layout_complete": True,
        "quiz_regenerated": True,
        "quiz_fallback_generated": True,
        "quiz_layout_issues": retry_issues or issues,
    }


def parse_time_plan(message):
    text = message.strip()
    planned = {}
    for canonical, aliases in TASK_PATTERNS:
        alias_group = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
        patterns = [
            rf"({alias_group})\s*[：:、，,\s]*([1-9]\d*)\s*分钟",
            rf"([1-9]\d*)\s*分钟\s*(?:的)?\s*({alias_group})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            values = [group for group in match.groups() if group and group.isdigit()]
            if values:
                planned[canonical] = int(values[0])
                break
    return [{"name": name, "minutes": planned[name]} for name, _ in TASK_PATTERNS if name in planned]


def plan_total_minutes(plan):
    return sum(int(task.get("minutes", 0)) for task in (plan or []))


def merge_remaining_time_plan(existing_plan, new_remaining_plan, remaining_names):
    by_name = {task["name"]: int(task.get("minutes", 0)) for task in (new_remaining_plan or [])}
    remaining_names = list(remaining_names or by_name.keys())
    merged = []
    for canonical, _ in TASK_PATTERNS:
        existing = next((task for task in (existing_plan or []) if task.get("name") == canonical), None)
        if canonical in remaining_names:
            merged.append({"name": canonical, "minutes": by_name.get(canonical, 0)})
        elif existing:
            merged.append({"name": canonical, "minutes": int(existing.get("minutes", 0))})
    return merged


def validate_overtime_replan(state, planned_tasks):
    expected_total = state.get("overtime_remaining_minutes")
    remaining_names = state.get("overtime_remaining_task_names") or [task["name"] for task in planned_tasks]
    provided_names = {task["name"] for task in planned_tasks}
    missing_names = [name for name in remaining_names if name not in provided_names]
    total = plan_total_minutes(planned_tasks)
    if expected_total is None:
        return {"ok": True, "total": total, "expectedTotal": total, "missingNames": []}
    return {
        "ok": total == int(expected_total) and not missing_names,
        "total": total,
        "expectedTotal": int(expected_total),
        "missingNames": missing_names,
    }


def is_complete_initial_time_plan(plan):
    if len(plan) != len(TASK_NAMES):
        return False
    names = {task["name"] for task in plan}
    total_minutes = plan_total_minutes(plan)
    return names == set(TASK_NAMES) and total_minutes == 20

def looks_like_time_plan(message):
    parsed_tasks = parse_time_plan(message)
    if len(parsed_tasks) >= 2:
        return True
    task_words = ["分析", "算法", "编程", "优化", "分钟"]
    if not contains_any(message, task_words):
        return False
    if "20" in message or "总计" in message or "一共" in message:
        return True
    minutes = [int(value) for value in re.findall(r"(\d+)\s*分钟", message)]
    return len(minutes) >= 4 and sum(minutes[:4]) == 20

def looks_like_replan(message):
    return contains_any(message, REPLAN_WORDS) and bool(parse_time_plan(message))

def looks_like_debug_failure(message):
    text = message or ""
    compact = re.sub(r"\s+", "", text)
    hard_failure_words = [
        word for word in DEBUG_FAILURE_WORDS
        if word not in {"报错", "错误", "bug", "Bug", "BUG"}
    ]
    if contains_any(text, hard_failure_words):
        return True
    if contains_any(text, ["没有报错", "无报错"]):
        return False
    if contains_any(text, ["报错", "错误", "bug", "Bug", "BUG"]):
        return True
    return bool(re.search(r"(?:不|没|未|无法|不会|不能|没法|仍然|还是).{0,8}(?:运行|执行|跑通|成功)", compact))

def looks_like_debug_success(message):
    if looks_like_debug_failure(message):
        return False
    return contains_any(message or "", DEBUG_SUCCESS_WORDS)

def looks_like_code_help(message):
    text = message or ""
    lowered = text.lower()
    if looks_like_debug_failure(text) or contains_any(text, CODE_HELP_WORDS):
        return True
    if "```" in lowered or "traceback" in lowered or "syntaxerror" in lowered:
        return True
    if re.search(r"\b(?:print|input|float|int|str|if|elif|else|for|while|def)\s*\(", lowered):
        return True
    if re.search(r"(?m)^\s*[a-zA-Z_]\w*\s*=", text):
        return True
    return False


def assistant_reflection_start_message():
    return (
        "我已经收到同伴的反馈：你的程序可以运行了。接下来我们直接进入反思阶段，"
        "一起完成学习评价和改进优化。\n\n"
        "第一步先核对本次学习计划。请你看一看：这次练习的目标是否已经完成？"
        "如果完成了，请写出你认为完成的证据；如果还没完全完成，也可以说明还差哪一点。"
    )

def assistant_confirms_quiz_pass(message):
    text = re.sub(r"\s+", "", message or "").replace("％", "%")
    if not text:
        return False
    negative_patterns = [
        r"前测通过[:：]?否",
        r"正确率[:：]?(?!100%)\d{1,2}%",
        r"未(?:达到|达)100%",
        r"没有(?:达到)?100%",
        r"还(?:没|未)有?全[部都]?答对",
        r"不能进入(?:任务拆解|时间分配|下一阶段)",
    ]
    if any(re.search(pattern, text) for pattern in negative_patterns):
        return False
    pass_patterns = [
        r"前测通过[:：]?是",
        r"正确率[:：]?100%",
        r"得分[:：]?100%",
        r"全部答对",
        r"全都答对",
        r"可以进入(?:任务拆解|时间分配|下一阶段)",
    ]
    return any(re.search(pattern, text) for pattern in pass_patterns)

def mentor_quiz_explanation_trigger(state, user_message, assistant_message):
    exercise = state.get("exercise_prompt") or "当前编程练习题干"
    return (
        "学生完成基础知识前测后存在错误。助教智能体已经负责批改并公布正确答案，"
        "现在请你作为编程导师智能体进行知识讲解。\n\n"
        f"练习任务题干：{exercise}\n"
        f"学生前测作答：{user_message}\n"
        f"助教批改与正确答案：{assistant_message}\n\n"
        "请只讲解学生出错题目背后的基础知识点，不要重新出题，不要进入任务拆解或时间分配。"
        "讲解要适合初中生：优先用生活化类比；如果涉及变量、输入输出、表达式或条件判断，"
        "可以给一个短小的Python代码案例。最后询问学生是否掌握，并提醒学生回复“我已掌握”后，助教会再出检验题。"
    )

def prepare_step_for_prompt(state, user_message):
    step = state.get("learning_step", "topic_intro")
    text = user_message.strip()
    if step == "quiz_explain_wait" and contains_any(text, ["掌握", "明白", "懂了", "会了"]):
        state["learning_phase"] = "掌握检验"
        state["learning_step"] = "quiz_review"

def update_learning_step(state, agent, user_message, assistant_message=""):
    step = state.get("learning_step", "topic_intro")
    phase = state.get("learning_phase", "主题作品体验")
    text = user_message.strip()
    metadata = {}

    if agent == "assistant" and step == "plan_allocation" and looks_like_time_plan(text):
        planned_tasks = parse_time_plan(text)
        if is_complete_initial_time_plan(planned_tasks):
            phase = "IPO问题分析"
            step = "ipo_analysis"
            state["plan_synced"] = True
            state["time_plan"] = planned_tasks
            metadata["start_timer"] = True
            metadata["plan_synced_to_peer"] = True
            metadata["time_plan"] = planned_tasks
            metadata["total_minutes"] = sum(task["minutes"] for task in planned_tasks)
        else:
            phase = "任务拆解与时间分配"
            step = "plan_allocation"
            metadata["time_plan_incomplete"] = True
            metadata["parsed_time_plan"] = planned_tasks
            metadata["total_minutes"] = sum(task["minutes"] for task in planned_tasks)
    elif agent == "peer" and (state.get("overtime_replan_pending") or looks_like_replan(text)) and looks_like_time_plan(text):
        planned_tasks = parse_time_plan(text)
        validation = validate_overtime_replan(state, planned_tasks)
        if validation["ok"]:
            remaining_names = state.get("overtime_remaining_task_names") or [task["name"] for task in planned_tasks]
            merged_plan = merge_remaining_time_plan(state.get("time_plan"), planned_tasks, remaining_names)
            if merged_plan:
                state["time_plan"] = merged_plan
            state["overtime_replan_pending"] = False
            metadata["reset_timer"] = True
            metadata["start_timer"] = True
            metadata["time_plan"] = merged_plan or planned_tasks
            metadata["total_minutes"] = validation["expectedTotal"]
            metadata["remaining_replan"] = True
            metadata["replan_current_index"] = int(state.get("overtime_current_index", 0))
            metadata["replan_completed_tasks"] = int(state.get("overtime_completed_tasks", metadata["replan_current_index"]))
        else:
            state["overtime_replan_pending"] = True
            metadata["replan_invalid"] = True
            metadata["replan_validation"] = validation
            metadata["parsed_time_plan"] = planned_tasks
    elif agent == "peer" and step == "debugging" and looks_like_debug_success(text):
        phase = "学习自评与报告"
        step = "self_evaluation"
        metadata["complete_timer"] = True
        metadata["pause_timer"] = True
        metadata["progress"] = 100
    elif step == "topic_intro" and agent == "assistant":
        state["current_topic"] = text[:80]
        phase = "主题作品体验"
        step = "experience_feedback"
    elif step == "experience_feedback" and contains_any(text, ["我已完成体验", "完成体验", "已体验", "体验完成"]):
        phase = "生活迁移思考"
        step = "life_connection"
    elif step == "life_connection" and agent == "assistant":
        phase = "练习题干输入"
        step = "exercise_intake"
    elif step == "exercise_intake" and agent == "assistant":
        state["exercise_prompt"] = text[:500]
        phase = "前测"
        step = "quiz"
    elif step == "quiz" and agent == "assistant":
        if assistant_confirms_quiz_pass(assistant_message):
            phase = "任务拆解与时间分配"
            step = "plan_allocation"
            metadata["quiz_passed"] = True
        else:
            phase = "前测讲解"
            step = "quiz_explain_wait"
            metadata["quiz_passed"] = False
            metadata["quiz_needs_mentor_explanation"] = True
    elif step == "quiz_review" and agent == "assistant":
        phase = "掌握检验"
        step = "quiz"
    elif step == "quiz_explain_wait" and agent in {"assistant", "mentor"}:
        phase = "前测讲解"
        step = "quiz_explain_wait"
    elif step == "ipo_analysis" and contains_any(text, ["IPO正确", "分析正确", "完全正确", "结束问题分析"]):
        phase = "流程图完善"
        step = "flowchart"
    elif step == "flowchart" and looks_like_numbered_flowchart_answer(text) and mentor_claims_flowchart_complete(assistant_message):
        phase = "代码编写与调试"
        step = "debugging"
    elif looks_like_debug_failure(text) or contains_any(text, ["报错", "错误", "bug", "调试", "Traceback", "SyntaxError", "TypeError", "NameError"]):
        phase = "代码编写与调试"
        step = "debugging"
    elif contains_any(text, REFLECTION_WORDS):
        phase = "学习自评与报告"
        step = "self_evaluation"
        metadata["reflection_available"] = True

    state["learning_phase"] = phase
    state["learning_step"] = step
    metadata["learning_step"] = step
    return phase, metadata

def decorate_message(state, agent, message, user_message):
    current_step = state.get("learning_step", "topic_intro")
    current_phase = state.get("learning_phase", "准备")
    phase = current_phase
    message = clean_reply(message)
    message = guard_algorithm_design_flowchart_format(state, agent, message)
    message = guard_premature_flowchart_completion(state, agent, user_message, message)
    message = guard_programming_stage_overguidance(state, agent, user_message, message)
    quiz_metadata = {}
    if should_format_quiz(agent, current_step):
        message, quiz_metadata = ensure_complete_quiz_message(state, agent, current_step, message)
    next_phase, metadata = update_learning_step(state, agent, user_message, message)
    metadata.update(quiz_metadata)
    if quiz_metadata.get("quiz_layout_complete") is False:
        phase = current_phase
        state["learning_phase"] = current_phase
        state["learning_step"] = current_step
        metadata["learning_step"] = current_step
    else:
        phase = next_phase
    debug_words = ["调试", "报错", "错误", "代码", "bug", "Bug", "BUG", "Traceback", "SyntaxError", "TypeError", "NameError"]
    if agent == "mentor" and any(k in user_message for k in debug_words):
        state["debug_count"] = int(state.get("debug_count", 0)) + 1
        metadata["debug_count"] = state["debug_count"]
        if state["debug_count"] >= 2:
            peer_message = (
                "学生已经连续调试了好几次。请你作为编程同伴智能体，先用简短、真诚的话鼓励学生，"
                "肯定他正在认真排查，再提醒他先稳住节奏，接下来导师会继续用提示帮他定位错误。"
            )
            peer_response = call_llm(state, "peer", peer_message)
            metadata["before_messages"] = [
                {
                    "agent": "peer",
                    "message": clean_reply(peer_response),
                    "phase": "代码编写与调试",
                    "trigger": "学生连续调试次数大于等于2",
                }
            ]
            metadata["peer_encouraged_before_debug"] = True
    if metadata.get("quiz_needs_mentor_explanation"):
        mentor_message = mentor_quiz_explanation_trigger(state, user_message, message)
        mentor_response = call_llm(state, "mentor", mentor_message)
        metadata["after_messages"] = [
            {
                "agent": "mentor",
                "message": clean_reply(mentor_response),
                "phase": "前测讲解",
                "trigger": "基础知识前测存在错误",
            }
        ]
        metadata["mentor_explained_quiz_errors"] = True
    if metadata.get("replan_invalid"):
        validation = metadata.get("replan_validation", {})
        missing = validation.get("missingNames") or []
        missing_text = f"还缺少：{'、'.join(missing)}。" if missing else ""
        message += (
            "\n\n系统提醒：这次剩余时间安排还没有同步到右侧计时器。"
            f"当前填写总计{validation.get('total', 0)}分钟，但剩余总时间应为{validation.get('expectedTotal', 0)}分钟。"
            f"{missing_text}"
            "请重新分配当前未完成任务和后续任务的时间，并让总计等于剩余总时间。"
        )
    if metadata.get("time_plan_incomplete"):
        parsed_summary = "、".join(f"{task['name']}{task['minutes']}分钟" for task in metadata.get("parsed_time_plan", []))
        parsed_hint = f"当前我识别到：{parsed_summary}。" if parsed_summary else "当前我还没有识别到完整的时间分配。"
        message += (
            "\n\n系统提醒：这次时间计划还没有同步给同伴智能体和右侧计时器。"
            f"{parsed_hint}"
            "请按四项任务重新回复完整计划，并让总计等于20分钟："
            "分析问题x分钟，设计算法x分钟，编写程序x分钟，代码优化x分钟。"
            "如果你写“设计程序”，系统会按“设计算法”处理。"
        )
    if metadata.get("plan_synced_to_peer"):
        total_minutes = metadata.get("total_minutes") or 20
        message += (
            f"\n\n学习计划已同步给编程同伴智能体。右侧计时器将按你分配的{total_minutes}分钟自动开始；"
            "接下来由编程导师智能体引导你完成IPO分析。每完成一个任务，直接告诉我“已完成”即可，"
            "同伴智能体会自动进入下一任务；你也可以使用右侧“进入下一任务”按钮手动推进。"
        )
    if agent == "peer" and any(k in user_message for k in ["没完成", "未完成", "超时", "时间已到", "倒计时已结束"]):
        metadata["overtime"] = True
        state["overtime_replan_pending"] = True
        message += (
            "\n\n请先停一下，重新分析这项任务为什么超时：是任务拆得太大、分析卡住、还是时间估计偏短。"
            "请直接回复剩余任务的新时间安排，例如“设计算法3分钟，编写程序6分钟，代码优化6分钟”。"
            "我会把右侧倒计时重置为新的剩余计划，并从第一项剩余任务开始计时。"
        )
    if agent == "peer" and metadata.get("reset_timer"):
        total_minutes = metadata.get("total_minutes") or 0
        message += f"\n\n新的剩余时间计划已同步到右侧倒计时，总计{total_minutes}分钟，现在重新开始计时。"
    if agent == "peer" and metadata.get("complete_timer"):
        message += "\n\n我已经帮你暂停倒计时，并把任务完成率更新到100%。接下来由编程助教智能体带你进入学习反思。"
        metadata["after_messages"] = (metadata.get("after_messages") or []) + [
            {
                "agent": "assistant",
                "message": assistant_reflection_start_message(),
                "phase": "学习自评与报告",
                "trigger": "学生反馈代码运行成功后自动进入反思阶段",
            }
        ]
        metadata["reflection_available"] = True
        metadata["assistant_started_reflection"] = True
    return clean_reply(message), phase, metadata

def maybe_append_auto_followup(state, agent, response, metadata):
    return clean_reply(response)
