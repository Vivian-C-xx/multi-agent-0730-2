import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from backend.config import SESSIONS
from backend.server import Handler
from backend.storage import init_storage


class ReflectionApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.environ["APP_DB_PATH"] = os.path.join(self.tmpdir.name, "api.db")
        init_storage()
        SESSIONS.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = None

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        SESSIONS.clear()
        self.tmpdir.cleanup()
        os.environ.pop("APP_DB_PATH", None)

    def request(self, method, path, payload=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        headers = {}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.cookie:
            headers["Cookie"] = self.cookie
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        cookie = response.getheader("Set-Cookie")
        if cookie:
            self.cookie = cookie.split(";", 1)[0]
        conn.close()
        return response.status, json.loads(raw)

    def test_reflection_init_save_and_report_api(self):
        status, data = self.request("POST", "/api/reflection/init", {})
        self.assertEqual(200, status)
        self.assertEqual("PLAN_REVIEW", data["currentStep"])

        status, data = self.request(
            "POST",
            "/api/reflection/save",
            {"step": "PLAN_REVIEW", "payload": {"studentGoalJudgement": "我完成了主要目标。"}},
        )
        self.assertEqual(200, status)
        self.assertEqual("WORK_SELF_EVALUATION", data["currentStep"])

        steps = [
            ("WORK_SELF_EVALUATION", {"runEffect": "能运行", "functionality": "主要功能完成", "codeStyle": "缩进清楚"}),
            ("WORK_EVIDENCE_FEEDBACK", {"studentFinalEvaluation": "我确认作品基本完成。"}),
            ("PROCESS_REVIEW", {"learningStrengths": ["能坚持排查"], "effectiveExperiences": ["先看报错"]}),
            ("PROBLEM_IDENTIFICATION", {"confirmedProblems": ["调试次数较多"]}),
            (
                "CAUSE_ANALYSIS",
                {"confirmedCauses": [{"problem": "调试次数较多", "selectedCause": "调试方法", "studentEvidence": "没有先看行号", "studentConfirmed": True}]},
            ),
            (
                "IMPROVEMENT_PLAN",
                {
                    "actions": [
                        {
                            "relatedProblem": "调试次数较多",
                            "relatedCause": "调试方法",
                            "action": "下次先记录报错行号，再检查变量名和缩进。",
                            "verification": "能在两次以内定位错误位置。",
                            "nextUseContext": "代码调试环节",
                        }
                    ]
                },
            ),
        ]
        for step, payload in steps:
            status, data = self.request("POST", "/api/reflection/save", {"step": step, "payload": payload})
            self.assertEqual(200, status)

        self.assertEqual("STUDENT_CONFIRMATION", data["currentStep"])
        status, report = self.request("POST", "/api/reflection/report", {"studentConfirmed": True})
        self.assertEqual(200, status)
        self.assertGreater(report["reportId"], 0)

        status, previous = self.request("GET", "/api/reflection/previous")
        self.assertEqual(200, status)
        self.assertEqual(report["reportId"], previous["reportId"])
        self.assertEqual("我完成了主要目标。", previous["previousReflection"]["goalAchievement"])
        self.assertEqual(
            "下次先记录报错行号，再检查变量名和缩进。",
            previous["previousReflection"]["improvementActions"][0]["action"],
        )


if __name__ == "__main__":
    unittest.main()
