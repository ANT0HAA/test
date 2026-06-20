"""
Общие фикстуры/утилиты для тестов.

Тесты НЕ требуют внешних сервисов (PostgreSQL / Ollama / сетевой ChromaDB):
LLM подменяется фейком, доступ к БД/БЗ не используется в покрытых путях.
"""
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel


def make_fake_llm_factory(answer: str, plan_decision=None):
    """
    Возвращает функцию-замену graph._llm: фейковая модель, которая стримит
    `answer` и (если передан plan_decision) отдаёт его на with_structured_output.
    """
    class _FakeStructured:
        def __init__(self, decision):
            self._decision = decision

        async def ainvoke(self, messages):
            return self._decision

    class _FakeChat(GenericFakeChatModel):
        def with_structured_output(self, schema, **kwargs):
            return _FakeStructured(plan_decision)

    def factory(streaming: bool = False):
        # бесконечный поток одинаковых сообщений
        return _FakeChat(messages=_repeat(AIMessage(content=answer)))

    return factory


def _repeat(msg):
    while True:
        yield msg
