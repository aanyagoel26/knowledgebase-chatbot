import time


class DatabaseAssistant:
    def answer_question(self, question: str):
        start_time = time.time()

        return {
            "answer": (
                "Database Assistant is connected. "
                "Next we will add schema reading, SQL generation, SQL validation, "
                "query execution, and table output."
            ),
            "sql": None,
            "columns": [],
            "rows": [],
            "execution_time": round(time.time() - start_time, 3)
        }


database_assistant = DatabaseAssistant()