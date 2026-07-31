const chatLog = document.querySelector("#chatLog");
const chatForm = document.querySelector("#chatForm");
const messageInput = document.querySelector("#messageInput");
const chips = document.querySelectorAll(".agent-chip");
const studentName = document.querySelector("#studentName");
const activeAgentName = document.querySelector("#activeAgentName");
const timerTask = document.querySelector("#timerTask");
const timerClock = document.querySelector("#timerClock");
const debugCount = document.querySelector("#debugCount");
const progressText = document.querySelector("#progressText");
const progressBar = document.querySelector("#progressBar");
const pauseTimerButton = document.querySelector("#pauseTimer");
const nextTaskButton = document.querySelector("#nextTask");
const timePlanHint = document.querySelector("#timePlanHint");
const reflectionPanel = document.querySelector("#reflectionPanel");
const reflectionBody = document.querySelector("#reflectionBody");
const reflectionStepText = document.querySelector("#reflectionStepText");
const reflectionProgressText = document.querySelector("#reflectionProgressText");
const reflectionProgressBar = document.querySelector("#reflectionProgressBar");
const reflectionError = document.querySelector("#reflectionError");
const reflectionBackButton = document.querySelector("#reflectionBack");
const reflectionSaveButton = document.querySelector("#reflectionSave");

let timer = null;
let timerStarted = false;
let taskIndex = 0;
const TOTAL_SECONDS = 20 * 60;
let secondsLeft = TOTAL_SECONDS;
let tasks = readTasks();
let activeTasks = null;
let reflectionState = null;
let reflectionSaving = false;

const agentLabels = [
  "编程自主学习管家",
  "编程助教智能体",
  "编程导师智能体",
  "编程同伴智能体",
];

function readTasks() {
  return [...document.querySelectorAll(".time-inputs input")].map((input) => ({
    name: input.dataset.task,
    minutes: Math.max(1, Number(input.value || 1)),
  }));
}

function totalPlannedMinutes() {
  return (activeTasks || readTasks()).reduce((sum, task) => sum + task.minutes, 0);
}

function renderTimePlanHint() {
  const total = totalPlannedMinutes();
  if (!timePlanHint) return;
  timePlanHint.textContent = `当前总计 ${total} 分钟，同伴会按这个计划倒计时。`;
  timePlanHint.classList.toggle("warning", total !== 20);
}

function setActiveAgent(agent) {
  chips.forEach((chip) => chip.classList.toggle("active", chip.dataset.agent === agent));
}

function addMessage(role, text, agent = "") {
  const node = document.createElement("div");
  node.className = `message ${role} ${agent}`;
  if (role === "user") {
    node.textContent = text;
  } else {
    const title = document.createElement("strong");
    title.textContent = agentName(agent);
    const body = renderBotMessageBody(stripAgentLabels(text));
    node.append(title, body);
  }
  chatLog.appendChild(node);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function normalizeQuizText(text) {
  return String(text || "")
    .replace(/(^|\n)\s*题目\s*(\d+)\s*[（(]\s*(?:单选|判断)\s*[）)]\s*/g, "$1$2. ")
    .replace(/\s+([A-D][.．、)）])\s*/g, "\n$1 ")
    .replace(/(（回答[“"']?对[”"']?或[“"']?错[”"']?）)/g, "\n$1")
    .replace(/(^|\n)(\d+\.\s*[^\n]+)\n(?=[A-D][.．、)）])/g, "$1$2\n\n")
    .replace(/(^|\n)(\d+\.\s*[^\n]+)\n(?=（回答)/g, "$1$2\n\n")
    .replace(/(^|\n)([A-D][.．、)）]\s*[^\n]+)\n(?=[A-D][.．、)）])/g, "$1$2\n\n")
    .replace(/(^|\n)([A-D][.．、)）]\s*[^\n]+)\n(?=\d+\.\s*)/g, "$1$2\n\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const reportSectionConfig = [
  { label: "完成目标", aliases: ["完成目标", "目标完成", "学习目标"], icon: "目" },
  { label: "自评分数", aliases: ["自评分数", "自评得分", "自我评价"], icon: "分" },
  { label: "主要问题", aliases: ["主要问题", "主要困难", "需要改进"], icon: "问" },
  { label: "改进计划", aliases: ["改进计划", "改进方案", "下一次行动"], icon: "改" },
  { label: "老师建议", aliases: ["老师建议", "助教建议", "学习建议"], icon: "建" },
  { label: "请你确认", aliases: ["请你确认", "确认方式", "确认"], icon: "认" },
];

function reportLabelPattern() {
  return reportSectionConfig
    .flatMap((section) => section.aliases)
    .map((label) => label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
}

function extractReportSections(text) {
  const normalized = String(text || "")
    .replace(new RegExp(`\\s*(${reportLabelPattern()})\\s*[：:]`, "g"), "\n$1：")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!/学习报告|报告摘要|个人报告/.test(normalized)) return null;
  const labelRegex = new RegExp(`(${reportLabelPattern()})\\s*[：:]`, "g");
  const matches = [...normalized.matchAll(labelRegex)];
  if (matches.length < 2) return null;
  const intro = normalized.slice(0, matches[0].index).trim();
  const sections = matches.map((match, index) => {
    const rawLabel = match[1];
    const start = match.index + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index : normalized.length;
    const config = reportSectionConfig.find((item) => item.aliases.includes(rawLabel)) || reportSectionConfig[0];
    return {
      label: config.label,
      icon: config.icon,
      content: normalized.slice(start, end).trim(),
    };
  }).filter((section) => section.content);
  return sections.length ? { intro, sections } : null;
}

function renderLearningReport(text) {
  const report = extractReportSections(text);
  if (!report) return null;
  const wrapper = document.createElement("div");
  wrapper.className = "learning-report";
  if (report.intro) {
    const intro = document.createElement("p");
    intro.className = "report-intro";
    intro.textContent = report.intro;
    wrapper.appendChild(intro);
  }
  report.sections.forEach((section) => {
    const item = document.createElement("div");
    item.className = "report-section";
    const icon = document.createElement("span");
    icon.className = "report-icon";
    icon.textContent = section.icon;
    const content = document.createElement("div");
    content.className = "report-content";
    const title = document.createElement("strong");
    title.textContent = section.label;
    const body = document.createElement("p");
    body.textContent = section.content;
    content.append(title, body);
    item.append(icon, content);
    wrapper.appendChild(item);
  });
  return wrapper;
}

function parseFlowchartMessage(text) {
  const lines = String(text || "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const markerIndex = lines.findIndex((line) => /^挖空流程图[：:]/.test(line));
  if (markerIndex < 0) return null;
  const nodes = [];
  let afterIndex = lines.length;
  for (let index = markerIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^[↓→-]+$/.test(line)) continue;
    if (/^(请回答|请按|如果你|如果当前|学生回答)/.test(line)) {
      afterIndex = index;
      break;
    }
    const match = line.match(/^（([^）]+)）\s*(.+)$/);
    if (match) {
      nodes.push({ shape: match[1], text: match[2] });
    }
  }
  if (nodes.length < 2) return null;
  return {
    intro: lines.slice(0, markerIndex).join("\n"),
    nodes,
    after: lines.slice(afterIndex).join("\n"),
  };
}

function flowchartShapeClass(node) {
  const shape = `${node.shape || ""} ${node.text || ""}`;
  if (/平行四边形|输入|输出/.test(shape)) return "flow-node-io";
  if (/圆角矩形|开始|结束/.test(shape)) return "flow-node-terminal";
  if (/菱形|判断/.test(shape)) return "flow-node-decision";
  return "flow-node-process";
}

function appendFlowchartText(target, text) {
  String(text || "").split(/(___\d+___)/g).forEach((part) => {
    if (!part) return;
    const node = document.createElement("span");
    node.textContent = part;
    if (/^___\d+___$/.test(part)) node.className = "flow-blank";
    target.appendChild(node);
  });
}

function renderFlowchartMessage(text) {
  const flowchart = parseFlowchartMessage(text);
  if (!flowchart) return null;
  const wrapper = document.createElement("div");
  wrapper.className = "flowchart-message";
  if (flowchart.intro) {
    const intro = document.createElement("p");
    intro.textContent = flowchart.intro;
    wrapper.appendChild(intro);
  }
  const diagram = document.createElement("div");
  diagram.className = "flowchart-diagram";
  flowchart.nodes.forEach((node, index) => {
    const item = document.createElement("div");
    item.className = `flow-node ${flowchartShapeClass(node)}`;
    appendFlowchartText(item, node.text);
    diagram.appendChild(item);
    if (index < flowchart.nodes.length - 1) {
      const arrow = document.createElement("div");
      arrow.className = "flow-arrow";
      arrow.textContent = "↓";
      diagram.appendChild(arrow);
    }
  });
  wrapper.appendChild(diagram);
  if (flowchart.after) {
    const after = document.createElement("p");
    after.className = "flowchart-answer-hint";
    after.textContent = flowchart.after;
    wrapper.appendChild(after);
  }
  return wrapper;
}

function renderBotMessageBody(text) {
  const normalized = normalizeQuizText(text);
  const report = renderLearningReport(normalized);
  if (report) return report;
  const flowchart = renderFlowchartMessage(normalized);
  if (flowchart) return flowchart;
  const body = document.createElement("p");
  body.textContent = normalized;
  return body;
}

function stripAgentLabels(text) {
  const labelPattern = agentLabels.join("|");
  const bracketed = new RegExp(`[【\\[]\\s*(?:${labelPattern})\\s*[】\\]]\\s*[:：]?\\s*`, "g");
  const bare = new RegExp(`(?:^|\\n)\\s*(?:${labelPattern})\\s*[:：]\\s*`, "g");
  return String(text || "")
    .replace(bracketed, "")
    .replace(bare, "\n")
    .trim();
}

function agentName(agent) {
  return {
    manager: "编程自主学习管家",
    assistant: "编程助教智能体",
    mentor: "编程导师智能体",
    peer: "编程同伴智能体",
  }[agent] || "智能体";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function statusText(item) {
  if (!item) return "暂无记录";
  if (item.available === false) return item.reason || "暂无记录";
  if (item.available === true) return JSON.stringify(item.value);
  return String(item);
}

async function sendMessage(message, agent = "auto") {
  addMessage("user", message);
  messageInput.value = "";
  messageInput.disabled = true;
  const waiting = document.createElement("div");
  waiting.className = "message bot";
  waiting.textContent = "正在思考...";
  chatLog.appendChild(waiting);
  chatLog.scrollTop = chatLog.scrollHeight;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, agent }),
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : {};
    waiting.remove();
    if (!res.ok) {
      addMessage("bot", data.error || "发送失败，请稍后重试。", "assistant");
      return;
    }
    setActiveAgent(data.agent);
    if (activeAgentName) {
      activeAgentName.textContent = data.agent_name || agentName(data.agent);
    }
    if (debugCount) {
      debugCount.textContent = data.debug_count || 0;
    }
    const metadata = data.metadata || {};
    if (Array.isArray(metadata.before_messages)) {
      metadata.before_messages.forEach((item) => {
        addMessage("bot", item.message || "", item.agent || "assistant");
      });
    }
    addMessage("bot", data.message || "智能体暂时没有返回内容，请再试一次。", data.agent);
    if (Array.isArray(metadata.after_messages)) {
      metadata.after_messages.forEach((item) => {
        addMessage("bot", item.message || "", item.agent || "assistant");
      });
      const lastMessage = metadata.after_messages[metadata.after_messages.length - 1];
      if (lastMessage?.agent) {
        setActiveAgent(lastMessage.agent);
        if (activeAgentName) {
          activeAgentName.textContent = agentName(lastMessage.agent);
        }
      }
    }
    if (metadata.start_timer) {
      applyTimePlan(metadata.time_plan, {
        replace: Boolean(metadata.reset_timer),
        currentIndex: metadata.remaining_replan ? Number(metadata.replan_current_index || 0) : 0,
        totalSeconds: metadata.remaining_replan ? Number(metadata.total_minutes || 0) * 60 : null,
      });
      startTimer();
    }
    if (metadata.complete_timer) {
      completeTimer();
    }
    if (metadata.reflection_available || metadata.reflection_step) {
      initReflection();
    }
  } catch (error) {
    waiting.remove();
    addMessage("bot", `请求失败：${error.message || "请检查后端服务是否正常运行。"}`, "assistant");
  } finally {
    messageInput.disabled = false;
    messageInput.focus();
  }
}

async function reflectionRequest(path, payload = null) {
  const options = payload
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    : { method: "GET" };
  const res = await fetch(path, options);
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok || data.ok === false) {
    const error = new Error(data.error || data.validation?.message || "反思数据保存失败，请稍后重试。");
    error.data = data;
    throw error;
  }
  return data;
}

async function initReflection() {
  if (!reflectionPanel) return;
  try {
    const data = await reflectionRequest("/api/reflection/init", {});
    reflectionState = data;
    renderReflection();
  } catch (error) {
    showReflectionError(error.message);
  }
}

function showReflectionError(message) {
  if (!reflectionError) return;
  reflectionError.textContent = message || "";
  reflectionError.classList.toggle("hidden", !message);
}

function currentReflectionStep() {
  return reflectionState?.currentStep || "PLAN_REVIEW";
}

function reflectionDraft(step = currentReflectionStep()) {
  return reflectionState?.draft?.[step] || {};
}

function renderReflection() {
  if (!reflectionPanel || !reflectionState) return;
  const step = currentReflectionStep();
  const steps = (reflectionState.steps || []).filter((item) => item !== "REFLECTION_INIT");
  const index = Math.max(0, steps.indexOf(step));
  const progress = Math.round(((index + 1) / steps.length) * 100);
  reflectionPanel.classList.remove("hidden");
  reflectionStepText.textContent = reflectionState.stepLabels?.[step] || step;
  reflectionProgressText.textContent = `${progress}%`;
  reflectionProgressBar.style.width = `${progress}%`;
  reflectionBackButton.disabled = index <= 0 || step === "REPORT_SAVED";
  reflectionSaveButton.disabled = step === "REPORT_SAVED";
  reflectionSaveButton.textContent = step === "STUDENT_CONFIRMATION" ? "确认并保存报告" : "保存并继续";
  showReflectionError("");

  const renderers = {
    PLAN_REVIEW: renderPlanReview,
    WORK_SELF_EVALUATION: renderWorkSelfEvaluation,
    WORK_EVIDENCE_FEEDBACK: renderWorkEvidenceFeedback,
    PROCESS_REVIEW: renderProcessReview,
    PROBLEM_IDENTIFICATION: renderProblemIdentification,
    CAUSE_ANALYSIS: renderCauseAnalysis,
    IMPROVEMENT_PLAN: renderImprovementPlan,
    STUDENT_CONFIRMATION: renderStudentConfirmation,
    REPORT_SAVED: renderReportSaved,
  };
  reflectionBody.innerHTML = (renderers[step] || renderPlanReview)();
}

function renderPlanReview() {
  const context = reflectionState.context || {};
  const draft = reflectionDraft("PLAN_REVIEW");
  const tasks = context.taskReview?.plannedTasks || [];
  const rows = tasks.length
    ? tasks.map((task) => `
        <tr>
          <td>${escapeHtml(task.name)}</td>
          <td>${escapeHtml(task.plannedMinutes)}分钟</td>
          <td>${task.completed ? "已完成" : "待确认"}</td>
          <td>${task.actualMinutes == null ? "暂无记录" : `${escapeHtml(task.actualMinutes)}分钟`}</td>
        </tr>`).join("")
    : `<tr><td colspan="4">系统数据：${escapeHtml(statusText(context.plannedTasks))}</td></tr>`;
  return `
    <div class="reflection-card">
      <span class="reflection-tag">系统数据</span>
      <h3>学习任务完成情况</h3>
      <table class="reflection-table">
        <thead><tr><th>任务</th><th>计划时间</th><th>完成状态</th><th>实际时间</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <p>实际时间为空表示当前记录无法判断，不代表你没有完成。</p>
    </div>
    <div class="reflection-card">
      <span class="reflection-tag">我的判断</span>
      <h3>你觉得目标完成了吗？</h3>
      <textarea data-reflection-field="studentGoalJudgement" rows="4" placeholder="例如：我完成了主要功能，但代码规范还想继续改进。">${escapeHtml(draft.studentGoalJudgement || "")}</textarea>
    </div>`;
}

function renderWorkSelfEvaluation() {
  const context = reflectionState.context || {};
  const draft = reflectionDraft("WORK_SELF_EVALUATION");
  const rubric = context.rubric || [];
  const items = rubric.map((item) => `<li>${escapeHtml(item.dimension)}：${escapeHtml(item.criteria)}</li>`).join("");
  return `
    <div class="reflection-card">
      <span class="reflection-tag">教师标准</span>
      <h3>作品评价标准</h3>
      <ul>${items || "<li>暂无教师配置标准，先使用系统默认的三项标准。</li>"}</ul>
    </div>
    <div class="reflection-card">
      <span class="reflection-tag">我的评价</span>
      <h3>请你先评价自己的作品</h3>
      <textarea data-reflection-field="runEffect" rows="3" placeholder="运行效果：程序运行起来了吗？输出像你预想的吗？">${escapeHtml(draft.runEffect || "")}</textarea>
      <textarea data-reflection-field="functionality" rows="3" placeholder="功能实现：主要功能完成了吗？还有哪些缺口？">${escapeHtml(draft.functionality || "")}</textarea>
      <textarea data-reflection-field="codeStyle" rows="3" placeholder="代码规范：变量名、缩进、结构是否清楚？">${escapeHtml(draft.codeStyle || "")}</textarea>
    </div>`;
}

function renderWorkEvidenceFeedback() {
  const context = reflectionState.context || {};
  const draft = reflectionDraft("WORK_EVIDENCE_FEEDBACK");
  const evidence = context.workEvidence?.objectiveEvidence || {};
  return `
    <div class="reflection-card">
      <span class="reflection-tag">系统数据</span>
      <h3>作品评价证据</h3>
      <p>运行结果：${escapeHtml(statusText(evidence.runResults))}</p>
      <p>测试结果：${escapeHtml(statusText(evidence.testResults))}</p>
      <p>静态检查：${escapeHtml(statusText(evidence.staticCodeChecks))}</p>
    </div>
    <div class="reflection-card">
      <span class="reflection-tag">助教建议</span>
      <p>${escapeHtml(context.workEvidence?.agentExplanation || "当前只解释已有证据，不猜测程序正确性。")}</p>
    </div>
    <div class="reflection-card">
      <span class="reflection-tag">我的确认</span>
      <h3>看完证据后，你要修改或确认自己的评价吗？</h3>
      <textarea data-reflection-field="studentFinalEvaluation" rows="4" placeholder="写下你最终确认的作品评价。">${escapeHtml(draft.studentFinalEvaluation || "")}</textarea>
    </div>`;
}

function renderProcessReview() {
  const context = reflectionState.context || {};
  const draft = reflectionDraft("PROCESS_REVIEW");
  const summary = context.processSummary || {};
  return `
    <div class="reflection-card">
      <span class="reflection-tag">系统数据</span>
      <h3>学习过程回顾</h3>
      <p>时间使用：${escapeHtml(summary.timeUse || "暂无记录")}</p>
      <p>调试次数：${escapeHtml(summary.debugCount ?? 0)}</p>
      <p>重要事件：${escapeHtml((summary.importantEvents || []).length ? `${summary.importantEvents.length}条记录` : "暂无明确事件记录")}</p>
    </div>
    <div class="reflection-card">
      <span class="reflection-tag">我的补充</span>
      <textarea data-reflection-field="learningStrengths" rows="3" placeholder="这次学习中你做得比较好的地方是什么？">${escapeHtml((draft.learningStrengths || []).join("\n") || draft.learningStrengths || "")}</textarea>
      <textarea data-reflection-field="effectiveExperiences" rows="3" placeholder="有哪些经验下次还可以继续使用？">${escapeHtml((draft.effectiveExperiences || []).join("\n") || draft.effectiveExperiences || "")}</textarea>
    </div>`;
}

function renderProblemIdentification() {
  const context = reflectionState.context || {};
  const draft = reflectionDraft("PROBLEM_IDENTIFICATION");
  const selected = new Set(draft.confirmedProblems || []);
  const options = (context.problemCues || []).map((cue, index) => `
    <label>
      <input type="checkbox" data-problem-index="${index}" ${selected.has(cue.description) ? "checked" : ""}>
      <span>${escapeHtml(cue.description)}<br><small>证据：${escapeHtml(cue.evidence)}</small></span>
    </label>`).join("");
  return `
    <div class="reflection-card">
      <span class="reflection-tag">可能需要反思的现象</span>
      <h3>请选择这次最想分析的问题</h3>
      <div class="reflection-options">${options}</div>
      <textarea data-reflection-field="extraProblem" rows="3" placeholder="如果系统没有说中，你可以自己补充一个主要问题。">${escapeHtml(draft.extraProblem || "")}</textarea>
    </div>`;
}

function renderCauseAnalysis() {
  const draft = reflectionDraft("CAUSE_ANALYSIS");
  const problemDraft = reflectionDraft("PROBLEM_IDENTIFICATION");
  const firstProblem = (problemDraft.confirmedProblems || [problemDraft.extraProblem || "请选择一个主要问题"])[0];
  return `
    <div class="reflection-card">
      <span class="reflection-tag">我的原因分析</span>
      <h3>先分析一个问题：${escapeHtml(firstProblem)}</h3>
      <p>助教不会替你决定原因。你可以从一个方向开始想，再写出自己的证据。</p>
      <select data-reflection-field="studentSelectedCause">
        ${["知识掌握", "任务理解", "程序设计方法", "调试方法", "时间管理", "学习投入"].map((item) => `<option ${draft.studentSelectedCause === item ? "selected" : ""}>${item}</option>`).join("")}
      </select>
      <textarea data-reflection-field="studentEvidence" rows="4" placeholder="你为什么这样判断？请写一个学习记录或具体表现。">${escapeHtml(draft.studentEvidence || "")}</textarea>
      <label><input type="checkbox" data-reflection-field="studentConfirmed" ${draft.studentConfirmed ? "checked" : ""}> 我确认这是本次主要原因之一</label>
    </div>`;
}

function renderImprovementPlan() {
  const draft = reflectionDraft("IMPROVEMENT_PLAN");
  const action = (draft.actions || [{}])[0];
  return `
    <div class="reflection-card">
      <span class="reflection-tag">我的改进方案</span>
      <h3>把改进写成下一次能做到的行动</h3>
      <input data-action-field="relatedProblem" placeholder="针对的问题" value="${escapeHtml(action.relatedProblem || "")}">
      <input data-action-field="relatedCause" placeholder="相关原因" value="${escapeHtml(action.relatedCause || "")}">
      <textarea data-action-field="action" rows="3" placeholder="下一次具体采取的行动，不写“认真一点”这种笼统话。">${escapeHtml(action.action || "")}</textarea>
      <textarea data-action-field="verification" rows="3" placeholder="如何判断措施有效？例如：运行前先用2组输入手算结果并对比。">${escapeHtml(action.verification || "")}</textarea>
      <input data-action-field="nextUseContext" placeholder="准备在哪个任务或环节使用" value="${escapeHtml(action.nextUseContext || "")}">
    </div>`;
}

function renderStudentConfirmation() {
  const draft = reflectionState.draft || {};
  return `
    <div class="reflection-card">
      <span class="reflection-tag">系统数据</span>
      <p>系统只保存当前记录中能看到的任务、时间、调试和交互证据。缺失的数据会标为暂无记录。</p>
    </div>
    <div class="reflection-card">
      <span class="reflection-tag">学生确认内容</span>
      <p>目标判断：${escapeHtml(draft.PLAN_REVIEW?.studentGoalJudgement || "未填写")}</p>
      <p>最终作品评价：${escapeHtml(draft.WORK_EVIDENCE_FEEDBACK?.studentFinalEvaluation || "未填写")}</p>
      <p>主要问题：${escapeHtml((draft.PROBLEM_IDENTIFICATION?.confirmedProblems || []).join("；") || draft.PROBLEM_IDENTIFICATION?.extraProblem || "未填写")}</p>
      <p>改进措施：${escapeHtml((draft.IMPROVEMENT_PLAN?.actions || []).map((item) => item.action).join("；") || "未填写")}</p>
      <label><input type="checkbox" data-reflection-field="studentConfirmed"> 我确认以上内容可以生成正式反思报告</label>
    </div>`;
}

function renderReportSaved() {
  return `
    <div class="reflection-card">
      <span class="reflection-tag">报告已保存</span>
      <h3>反思报告已经保存</h3>
      <p>下一轮制定计划时，管家会读取这次确认的改进措施，帮助你把反思用到新的学习任务里。</p>
    </div>`;
}

function collectReflectionPayload(step) {
  const payload = {};
  reflectionBody.querySelectorAll("[data-reflection-field]").forEach((field) => {
    const key = field.dataset.reflectionField;
    payload[key] = field.type === "checkbox" ? field.checked : field.value.trim();
  });
  if (step === "PROCESS_REVIEW") {
    payload.learningStrengths = String(payload.learningStrengths || "").split(/\n+/).map((item) => item.trim()).filter(Boolean);
    payload.effectiveExperiences = String(payload.effectiveExperiences || "").split(/\n+/).map((item) => item.trim()).filter(Boolean);
  }
  if (step === "PROBLEM_IDENTIFICATION") {
    const cues = reflectionState.context?.problemCues || [];
    payload.confirmedProblems = [...reflectionBody.querySelectorAll("[data-problem-index]:checked")]
      .map((item) => cues[Number(item.dataset.problemIndex)]?.description)
      .filter(Boolean);
    if (payload.extraProblem) payload.confirmedProblems.push(payload.extraProblem);
  }
  if (step === "CAUSE_ANALYSIS") {
    const problemDraft = reflectionDraft("PROBLEM_IDENTIFICATION");
    payload.confirmedCauses = [
      {
        problem: (problemDraft.confirmedProblems || [problemDraft.extraProblem || "主要问题"])[0],
        selectedCause: payload.studentSelectedCause,
        studentEvidence: payload.studentEvidence,
        studentConfirmed: Boolean(payload.studentConfirmed),
      },
    ];
  }
  if (step === "IMPROVEMENT_PLAN") {
    const action = {};
    reflectionBody.querySelectorAll("[data-action-field]").forEach((field) => {
      action[field.dataset.actionField] = field.value.trim();
    });
    payload.actions = [action];
  }
  return payload;
}

async function saveReflectionStep() {
  if (!reflectionState || reflectionSaving) return;
  const step = currentReflectionStep();
  const payload = collectReflectionPayload(step);
  if (step === "WORK_SELF_EVALUATION" && (!payload.runEffect || !payload.functionality || !payload.codeStyle)) {
    showReflectionError("请先完成三个维度的自评，再查看系统证据。");
    return;
  }
  if (step === "STUDENT_CONFIRMATION") {
    if (!payload.studentConfirmed) {
      showReflectionError("需要你主动勾选确认后，系统才会保存正式反思报告。");
      return;
    }
    return saveReflectionReport(payload);
  }
  reflectionSaving = true;
  reflectionSaveButton.disabled = true;
  try {
    reflectionState = await reflectionRequest("/api/reflection/save", { step, payload });
    renderReflection();
  } catch (error) {
    showReflectionError(error.message);
  } finally {
    reflectionSaving = false;
    reflectionSaveButton.disabled = false;
  }
}

async function saveReflectionReport(payload) {
  reflectionSaving = true;
  reflectionSaveButton.disabled = true;
  try {
    const data = await reflectionRequest("/api/reflection/report", {
      studentConfirmed: true,
      ...payload,
    });
    reflectionState.currentStep = "REPORT_SAVED";
    reflectionState.report = data.report;
    renderReflection();
  } catch (error) {
    showReflectionError(error.message);
  } finally {
    reflectionSaving = false;
    reflectionSaveButton.disabled = false;
  }
}

async function backReflectionStep() {
  if (!reflectionState || reflectionSaving) return;
  try {
    reflectionState = await reflectionRequest("/api/reflection/back", {});
    renderReflection();
  } catch (error) {
    showReflectionError(error.message);
  }
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (message) sendMessage(message);
});

function normalizeTimePlan(timePlan) {
  return (Array.isArray(timePlan) ? timePlan : [])
    .map((task) => ({
      name: task.name,
      minutes: Math.max(1, Number(task.minutes || 1)),
    }))
    .filter((task) => task.name && task.minutes > 0);
}

function applyTimePlan(timePlan, options = {}) {
  const normalized = normalizeTimePlan(timePlan);
  if (normalized.length === 0) return;
  const inputs = [...document.querySelectorAll(".time-inputs input")];
  normalized.forEach((task) => {
    const input = inputs.find((item) => item.dataset.task === task.name);
    if (input) input.value = task.minutes;
  });
  clearInterval(timer);
  timer = null;
  timerStarted = false;
  activeTasks = options.replace ? normalized : null;
  taskIndex = Math.min(Math.max(0, Number(options.currentIndex || 0)), normalized.length - 1);
  tasks = activeTasks || readTasks();
  secondsLeft = Number(options.totalSeconds || 0) > 0 ? Number(options.totalSeconds) : TOTAL_SECONDS;
  renderTimePlanHint();
  renderTimer();
}

chips.forEach((chip) => {
  chip.type = "button";
});

studentName.addEventListener("change", async () => {
  await fetch("/api/student-name", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: studentName.value.trim() }),
  });
});

document.querySelectorAll(".time-inputs input").forEach((input) => {
  input.addEventListener("change", () => {
    input.value = clampTaskMinutes(input.value, input.min, input.max);
    activeTasks = null;
    tasks = readTasks();
    renderTimePlanHint();
    if (!timerStarted) {
      taskIndex = 0;
      secondsLeft = TOTAL_SECONDS;
      renderTimer();
    }
  });
});

document.querySelectorAll("[data-time-action]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = button.closest(".time-stepper")?.querySelector("input");
    if (!input) return;
    const direction = button.dataset.timeAction === "increment" ? 1 : -1;
    input.value = clampTaskMinutes(Number(input.value || 0) + direction, input.min, input.max);
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
});

function clampTaskMinutes(value, min, max) {
  const lower = Number(min || 1);
  const upper = Number(max || 20);
  const nextValue = Math.round(Number(value || lower));
  return Math.min(upper, Math.max(lower, nextValue));
}

function completedPlannedMinutes() {
  return tasks
    .slice(0, taskIndex)
    .reduce((sum, task) => sum + task.minutes, 0);
}

function renderTimer() {
  const task = tasks[taskIndex] || { name: "学习完成", minutes: 0 };
  timerTask.textContent = taskIndex < tasks.length ? `当前任务：${task.name}` : "全部任务已结束";
  const minutes = String(Math.floor(secondsLeft / 60)).padStart(2, "0");
  const seconds = String(secondsLeft % 60).padStart(2, "0");
  timerClock.textContent = `${minutes}:${seconds}`;
  const total = tasks.reduce((sum, item) => sum + item.minutes, 0);
  const progress = total ? Math.min(100, Math.round((completedPlannedMinutes() / total) * 100)) : 0;
  if (progressText) progressText.textContent = `${progress}%`;
  if (progressBar) progressBar.style.width = `${progress}%`;
  renderTimerButton();
}

function renderTimerButton() {
  if (!pauseTimerButton) return;
  const finished = taskIndex >= tasks.length || secondsLeft <= 0;
  pauseTimerButton.disabled = finished;
  if (!timerStarted) {
    pauseTimerButton.textContent = "开始计时";
  } else {
    pauseTimerButton.textContent = timer ? "暂停计时" : "继续计时";
  }
}

function startTimer() {
  tasks = activeTasks || readTasks();
  if (!tasks.length) return;
  if (taskIndex >= tasks.length) taskIndex = 0;
  if (!secondsLeft || secondsLeft <= 0) secondsLeft = TOTAL_SECONDS;
  timerStarted = true;
  renderTimePlanHint();
  renderTimer();
  clearInterval(timer);
  timer = setInterval(() => {
    secondsLeft -= 1;
    renderTimer();
    if (secondsLeft <= 0) {
      clearInterval(timer);
      timer = null;
      renderTimerButton();
      sendMessage(
        `当前任务“${tasks[taskIndex].name}”倒计时已结束，我还没有确认完成，属于超时未完成。请编程同伴智能体监督我重新分析任务时间，并帮我调整接下来的学习节奏。`,
        "peer"
      );
    }
  }, 1000);
  renderTimerButton();
}

function completeTimer() {
  clearInterval(timer);
  timer = null;
  timerStarted = false;
  tasks = activeTasks || readTasks();
  taskIndex = tasks.length;
  secondsLeft = 0;
  renderTimer();
}

function toggleTimerPause() {
  if (timer) {
    clearInterval(timer);
    timer = null;
    renderTimerButton();
    return;
  }
  startTimer();
}

function nextTask() {
  clearInterval(timer);
  timer = null;
  const shouldResume = timerStarted && secondsLeft > 0;
  taskIndex += 1;
  if (taskIndex < tasks.length) {
    renderTimer();
    if (shouldResume) startTimer();
    if (tasks[taskIndex].name === "设计算法") {
      sendMessage("我已经结束问题分析任务，请导师根据我的 IPO 总结生成流程图框架。");
    }
  } else {
    secondsLeft = 0;
    renderTimer();
    sendMessage("我已完成相关知识的学习，请对我的学习进行评价。");
  }
}

pauseTimerButton.addEventListener("click", toggleTimerPause);
nextTaskButton.addEventListener("click", nextTask);
if (reflectionSaveButton) reflectionSaveButton.addEventListener("click", saveReflectionStep);
if (reflectionBackButton) reflectionBackButton.addEventListener("click", backReflectionStep);
renderTimePlanHint();
renderTimer();
