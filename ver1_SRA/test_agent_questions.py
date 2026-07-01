import unittest

from main import _direct_answer
from generate_students import SessionLocal, get_student_subject_mark, update_marks as update_marks_query


class AgentQuestionRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def answer(self, question, role="Admin", user_id=1):
        result = _direct_answer(question, self.db, role=role, user_id=user_id)
        self.assertIsNotNone(result, f"Question fell through to the LLM: {question}")
        return result

    def set_priya_subject_grade(self, subject_code, grade, grade_point):
        current = get_student_subject_mark(self.db, 83, subject_code)
        self.assertIsNotNone(current)
        update_marks_query(self.db, 1, {
            "student_id": 83,
            "semester": 5,
            "subject_code": subject_code,
            "marks": current["marks"],
            "grade": grade,
            "grade_point": grade_point,
        })

    def test_q1_search_priya_multiple_results(self):
        answer = self.answer("Search for students named Priya.")
        self.assertIn("Found", answer)
        self.assertIn("Priya Menon", answer)
        self.assertIn("ID 83", answer)

    def test_q2_complete_details_priya_menon(self):
        answer = self.answer("Show the complete details of Priya Menon.")
        self.assertIn("Student 83: Priya Menon", answer)
        self.assertIn("Academic record:", answer)
        self.assertIn("CSE-S05-04 Cloud Computing", answer)

    def test_q3_semester_5_subjects_priya_menon(self):
        answer = self.answer("List all subjects taken by Priya Menon in Semester 5.")
        self.assertIn("Priya Menon took these subjects in Semester 5:", answer)
        self.assertIn("CSE-S05-04 Cloud Computing", answer)

    def test_q4_subject_specific_marks(self):
        answer = self.answer("What marks did Priya Menon score in CSE-S05-04?")
        self.assertIn("Priya Menon scored", answer)
        self.assertIn("Cloud Computing (CSE-S05-04)", answer)
        self.assertIn("marks", answer)

    def test_q5_update_grade_and_verify_marks(self):
        answer = self.answer("Update Priya Menon's CSE-S05-04 grade to A and then show the updated marks.")
        self.assertIn("Updated Priya Menon's grade in CSE-S05-04 to A.", answer)
        self.assertIn("Her marks remain", answer)
        self.assertIn("updated grade point is 9.0", answer)

    def test_q5_update_grade_denied_for_non_admin(self):
        answer = self.answer(
            "Update Priya Menon's CSE-S05-04 grade to A and then show the updated marks.",
            role="Assistant",
            user_id=2,
        )
        self.assertEqual("Only Admins can update marks or grades.", answer)

    def test_q6_count_semester_6_does_not_infer_from_year(self):
        answer = self.answer("How many students are currently in Semester 6?")
        self.assertEqual("There are 120 students in semester 6.", answer)

    def test_q7_count_first_year_cse(self):
        answer = self.answer("How many first-year CSE students are there?")
        self.assertEqual("There are 30 first-year CSE students.", answer)

    def test_q8_list_students_in_subject(self):
        answer = self.answer("List all students enrolled in CSE-S05-04.")
        self.assertIn("students have records for CSE-S05-04 (Cloud Computing):", answer)
        self.assertIn("ID 83: Priya Menon", answer)

    def test_q9_audit_logs_admin_only(self):
        admin_answer = self.answer("Show the audit logs for student ID 83.")
        self.assertIn("Audit logs for student ID 83:", admin_answer)

        assistant_answer = self.answer("Show the audit logs for student ID 83.", role="Assistant", user_id=2)
        self.assertEqual("Only Admins can view audit logs.", assistant_answer)

    def test_q10_invalid_student_id(self):
        answer = self.answer("Show the details of student ID 9999.")
        self.assertEqual("Student not found: no student exists with ID 9999.", answer)

    def test_round2_q1_disambiguate_priya_semester_subjects_and_cgpa(self):
        answer = self.answer(
            "Search for students named Priya. Choose the Priya in the CSE branch who is currently in the 6th semester, list her Semester 5 subjects, and tell me her CGPA."
        )
        self.assertIn("Selected Priya Menon (ID 83)", answer)
        self.assertIn("CGPA:", answer)
        self.assertIn("Semester 5 subjects:", answer)
        self.assertIn("CSE-S05-01 Machine Learning", answer)
        self.assertIn("CSE-S05-04 Cloud Computing", answer)

    def test_round2_q2_update_grade_recalculate_cgpa_and_show_changed_only(self):
        self.set_priya_subject_grade("CSE-S05-01", "A", 9.0)
        answer = self.answer(
            "Update Priya Menon's CSE-S05-01 grade from A to C. Then recalculate her CGPA and show me only the subjects whose grades changed as a result."
        )
        self.assertIn("Updated Priya Menon's CSE-S05-01 grade to C.", answer)
        self.assertIn("Recalculated CGPA:", answer)
        self.assertIn("Subjects whose grades changed:", answer)
        self.assertIn("CSE-S05-01 Machine Learning: A to C", answer)
        self.assertNotIn("CSE-S05-02 Web Technologies", answer)

    def test_round2_q3_highest_semester_6_branch_count(self):
        answer = self.answer("Which branch has the highest number of students currently in Semester 6?")
        self.assertIn("currently in Semester 6", answer)
        self.assertIn("CSE: 30", answer)
        self.assertIn("ECE: 30", answer)
        self.assertIn("ME: 30", answer)
        self.assertIn("CE: 30", answer)

    def test_round2_q4_priya_marks_update_audit_logs(self):
        answer = self.answer("Show me all audit log entries related to marks updates for Priya Menon.")
        self.assertIn("Marks update audit logs for Priya Menon (ID 83):", answer)
        self.assertIn("changed", answer)
        self.assertIn("grade", answer)

    def test_round2_q4_priya_marks_update_audit_logs_denied_for_non_admin(self):
        answer = self.answer(
            "Show me all audit log entries related to marks updates for Priya Menon.",
            role="Assistant",
            user_id=2,
        )
        self.assertEqual("Only Admins can view audit logs.", answer)

    def test_round2_q5_subject_roster_highest_and_average(self):
        answer = self.answer(
            "List every student enrolled in CSE-S05-04 and tell me who scored the highest and what the class average is."
        )
        self.assertIn("60 students are enrolled in CSE-S05-04 (Cloud Computing).", answer)
        self.assertIn("Highest score: 94, by Nithya Patel.", answer)
        self.assertIn("Class average: 63.6 marks.", answer)
        self.assertIn("ID 83: Priya Menon, 82 marks, grade A", answer)


if __name__ == "__main__":
    unittest.main()
