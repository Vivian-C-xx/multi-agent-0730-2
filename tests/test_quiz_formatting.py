import unittest
from unittest.mock import patch

from backend.services.learning_flow import (
    ensure_complete_quiz_message,
    format_quiz_layout,
    quiz_layout_issues,
)


class QuizFormattingTest(unittest.TestCase):
    def test_inline_options_are_split_to_separate_lines(self):
        raw = "题目1（单选） 在计算BMI时，哪个输入正确？ A. height B. weight C. print D. input"
        formatted = format_quiz_layout(raw)
        lines = [line.strip() for line in formatted.splitlines() if line.strip()]
        self.assertEqual("1. 在计算BMI时，哪个输入正确？", lines[0])
        self.assertIn("A. height", lines)
        self.assertIn("B. weight", lines)
        self.assertIn("C. print", lines)
        self.assertIn("D. input", lines)
        self.assertIn("1. 在计算BMI时，哪个输入正确？\n\nA. height\n\nB. weight", formatted)

    def test_judgement_hint_is_split_to_own_line(self):
        raw = "题目2（判断） 计算BMI前需要先得到身高。（回答“对”或“错”）"
        formatted = format_quiz_layout(raw)
        self.assertIn("2. 计算BMI前需要先得到身高。\n\n（回答“对”或“错”）", formatted)

    def test_missing_single_choice_options_are_detected(self):
        raw = "题目1（单选） 顺序结构是什么？\nA. 从上到下\nB. 随机执行\nC. 只执行最后一行"
        issues = quiz_layout_issues(raw)
        self.assertEqual(["D"], issues[0]["missingOptions"])

    def test_incomplete_quiz_is_regenerated_once(self):
        incomplete = "题目1（单选） 顺序结构是什么？ A. 从上到下 B. 随机执行"
        regenerated = "1. 顺序结构最主要的特点是（）\n\nA. 从上到下执行\n\nB. 从下到上执行\n\nC. 随机执行\n\nD. 只执行最后一行"
        with patch("backend.services.learning_flow.call_llm", return_value=regenerated):
            message, metadata = ensure_complete_quiz_message({}, "assistant", "exercise_intake", incomplete)
        self.assertTrue(metadata["quiz_layout_complete"])
        self.assertTrue(metadata["quiz_regenerated"])
        self.assertIn("1. 顺序结构最主要的特点是（）", message)
        self.assertIn("D. 只执行最后一行", message)

    def test_code_block_quiz_is_regenerated(self):
        incomplete = "1. 执行下面代码输出什么？\n```python\nprint(1)\n```\nA. 1\nB. 2\nC. 报错\nD. 空白"
        regenerated = "1. print(1) 的输出是（）\n\nA. 1\n\nB. 2\n\nC. 报错\n\nD. 空白"
        with patch("backend.services.learning_flow.call_llm", return_value=regenerated):
            message, metadata = ensure_complete_quiz_message({}, "assistant", "exercise_intake", incomplete)
        self.assertTrue(metadata["quiz_layout_complete"])
        self.assertTrue(metadata["quiz_regenerated"])
        self.assertNotIn("```", message)

    def test_incomplete_quiz_uses_local_fallback_after_failed_retry(self):
        incomplete = "题目1（单选） 顺序结构是什么？ A. 从上到下 B. 随机执行"
        with patch("backend.services.learning_flow.call_llm", return_value=incomplete):
            message, metadata = ensure_complete_quiz_message(
                {"exercise_prompt": "我要设计一个计算BMI值的程序"},
                "assistant",
                "exercise_intake",
                incomplete,
            )
        self.assertTrue(metadata["quiz_layout_complete"])
        self.assertTrue(metadata["quiz_fallback_generated"])
        self.assertIn("1. 在计算BMI的程序中", message)
        self.assertIn("D. 删除变量", message)

    def test_llm_error_is_not_masked_as_incomplete_options(self):
        error = "还没有配置 DeepSeek API 密钥。请在 .env 中设置 DEEPSEEK_API_KEY 后重新启动。"
        message, metadata = ensure_complete_quiz_message({}, "assistant", "exercise_intake", error)
        self.assertFalse(metadata["quiz_layout_complete"])
        self.assertTrue(metadata["quiz_llm_error"])
        self.assertIn("DeepSeek API 密钥", message)


if __name__ == "__main__":
    unittest.main()
