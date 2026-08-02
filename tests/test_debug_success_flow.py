import unittest

from backend.agents.router_agent import route_agent
from backend.services.learning_flow import (
    decorate_message,
    guard_algorithm_design_flowchart_format,
    guard_premature_flowchart_completion,
    guard_programming_stage_overguidance,
    looks_like_debug_failure,
    looks_like_debug_success,
)


class DebugSuccessFlowTest(unittest.TestCase):
    def test_success_run_words_are_detected(self):
        self.assertTrue(looks_like_debug_success("代码已经成功运行了"))
        self.assertTrue(looks_like_debug_success("程序跑通了，没有报错"))
        self.assertFalse(looks_like_debug_success("我的代码还是不能运行"))
        self.assertTrue(looks_like_debug_failure("我的代码还是不能运行"))

    def test_success_run_routes_to_peer_before_mentor(self):
        state = {"learning_step": "debugging", "learning_phase": "代码编写与调试"}
        message = 'print("ok") 成功运行了'
        self.assertEqual("peer", route_agent(message, state))

    def test_code_that_cannot_run_routes_to_mentor(self):
        state = {"learning_step": "debugging", "learning_phase": "代码编写与调试"}
        message = 'a=input("请输入身高") b=input("请输入体重") bmi=b/(a*a) 我的代码还是不能运行'
        self.assertEqual("mentor", route_agent(message, state))

    def test_code_failure_does_not_enter_reflection(self):
        state = {"learning_step": "debugging", "learning_phase": "代码编写与调试"}
        _, phase, metadata = decorate_message(
            state,
            "mentor",
            "先看报错位置，再检查输入值的数据类型。",
            'a=input("请输入身高") b=input("请输入体重") bmi=b/(a*a) 我的代码还是不能运行',
        )
        self.assertEqual("代码编写与调试", phase)
        self.assertEqual("debugging", state["learning_step"])
        self.assertNotIn("complete_timer", metadata)
        self.assertNotIn("reflection_available", metadata)

    def test_peer_success_auto_starts_assistant_reflection(self):
        state = {"learning_step": "debugging", "learning_phase": "代码编写与调试"}
        response, phase, metadata = decorate_message(
            state,
            "peer",
            "太好了，你的程序运行成功了。",
            "代码成功运行了",
        )
        self.assertEqual("学习自评与报告", phase)
        self.assertEqual("self_evaluation", state["learning_step"])
        self.assertTrue(metadata["complete_timer"])
        self.assertTrue(metadata["reflection_available"])
        self.assertEqual("assistant", metadata["after_messages"][0]["agent"])
        self.assertIn("进入反思阶段", metadata["after_messages"][0]["message"])
        self.assertIn("助教", response)

    def test_flowchart_completion_requires_numbered_blank_answers(self):
        state = {"learning_step": "flowchart", "learning_phase": "流程图完善"}
        guarded = guard_premature_flowchart_completion(
            state,
            "mentor",
            "开始 输入身高 输入体重 计算BMI 输出BMI值",
            "回答正确！所有空白都填对了。第四步流程图框架补全完成。请进入第五步。",
        )
        self.assertIn("还没有按空白编号逐项填写", guarded)
        self.assertNotIn("进入第五步", guarded)

    def test_flowchart_numbered_blank_answers_can_pass_guard(self):
        state = {"learning_step": "flowchart", "learning_phase": "流程图完善"}
        original = "回答正确！所有空白都填对了。第四步流程图框架补全完成。"
        guarded = guard_premature_flowchart_completion(
            state,
            "mentor",
            "___1___：平行四边形\n___2___：weight / (height * height)\n___3___：BMI值\n___4___：结束",
            original,
        )
        self.assertEqual(original, guarded)

    def test_flowchart_stage_does_not_advance_without_numbered_answers(self):
        state = {"learning_step": "flowchart", "learning_phase": "流程图完善"}
        response, phase, metadata = decorate_message(
            state,
            "mentor",
            "回答正确！所有空白都填对了。第四步流程图框架补全完成。请进入第五步。",
            "开始 输入身高 输入体重 计算BMI 输出BMI值",
        )
        self.assertEqual("flowchart", state["learning_step"])
        self.assertEqual("流程图完善", phase)
        self.assertIn("还没有按空白编号逐项填写", response)

    def test_algorithm_design_replaces_code_blank_with_flowchart(self):
        state = {
            "learning_step": "flowchart",
            "learning_phase": "流程图完善",
            "exercise_prompt": "设计一个计算BMI值的程序",
        }
        guarded = guard_algorithm_design_flowchart_format(
            state,
            "mentor",
            "现在进入第二步任务“设计算法”。请补全Python代码。\nheight = ______\nweight = ______\nbmi = ______\n提示：使用input()和float()",
        )
        self.assertIn("挖空流程图", guarded)
        self.assertIn("（平行四边形）输入 ___1___、___2___", guarded)
        self.assertIn("（矩形）计算：BMI = ___3___", guarded)
        self.assertNotIn("height = ______", guarded)
        self.assertNotIn("Python代码", guarded)

    def test_flowchart_stage_advances_after_numbered_answers_and_confirmation(self):
        state = {"learning_step": "flowchart", "learning_phase": "流程图完善"}
        _, phase, _ = decorate_message(
            state,
            "mentor",
            "回答正确！所有空白都填对了。第四步流程图框架补全完成。请进入第五步。",
            "___1___：平行四边形\n___2___：weight / (height * height)\n___3___：BMI值\n___4___：结束",
        )
        self.assertEqual("debugging", state["learning_step"])
        self.assertEqual("代码编写与调试", phase)

    def test_programming_stage_ready_message_gets_self_coding_prompt(self):
        state = {
            "learning_step": "debugging",
            "learning_phase": "代码编写与调试",
            "exercise_prompt": "设计一个计算BMI值的程序",
        }
        guarded = guard_programming_stage_overguidance(
            state,
            "mentor",
            "我准备好了",
            "好的，我们先从第一步开始：输入身高。请写出这一句代码。",
        )
        self.assertIn("自己写出完整 Python 程序", guarded)
        self.assertIn("把代码和运行结果发给我", guarded)
        self.assertNotIn("请写出这一句代码", guarded)

    def test_programming_stage_keeps_debug_feedback_for_errors(self):
        state = {"learning_step": "debugging", "learning_phase": "代码编写与调试"}
        original = "请先观察报错行号，再检查变量名。"
        guarded = guard_programming_stage_overguidance(
            state,
            "mentor",
            "运行报错 SyntaxError",
            original,
        )
        self.assertEqual(original, guarded)

    def test_flowchart_completion_marks_step_change_without_extra_timer_advance(self):
        state = {"learning_step": "flowchart", "learning_phase": "流程图完善"}
        response, _, metadata = decorate_message(
            state,
            "mentor",
            "回答正确！所有空白都填对了。第四步流程图框架补全完成。请进入第五步：编写程序。",
            "___1___：身高\n___2___：体重\n___3___：weight / (height * height)\n___4___：BMI值",
        )
        self.assertEqual("debugging", state["learning_step"])
        self.assertTrue(metadata["learning_step_changed"])
        self.assertEqual("flowchart", metadata["previous_learning_step"])
        self.assertIn("第三步任务“编写程序”", response)

    def test_programming_prompt_mentions_turtle_editor(self):
        state = {"learning_step": "debugging", "learning_phase": "代码编写与调试"}
        guarded = guard_programming_stage_overguidance(
            state,
            "mentor",
            "我准备好了",
            "请写出第一行代码。",
        )
        self.assertIn("海龟编辑器", guarded)


if __name__ == "__main__":
    unittest.main()
