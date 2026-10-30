"""Store policy: parse policy.md into citable sub-sections and pick the one that answers a question.

The LLM only chooses section IDs, from an enum of the real IDs, or says the policy doesn't cover the question.
The answer text is the section's own wording, so nothing about the policy is generated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from src.config import DATA_DIR
from src.models.llm import LLM, LLMUsage


@dataclass(frozen=True)
class PolicySection:
    id: str      # "1.2"
    title: str   # "Free returns, no restocking fee"
    text: str    # body, markdown emphasis removed


def load_policy(path=DATA_DIR / "policy.md") -> list[PolicySection]:
    sections, current, body = [], None, []
    for line in path.read_text(encoding="utf-8").splitlines() + ["## end"]:  # sentinel flushes the last section
        if line.startswith("### ") or line.startswith("## "):
            if current:
                sections.append(PolicySection(current[0], current[1], " ".join(body).replace("**", "").strip()))
            current, body = None, []
            if m := re.match(r"^###\s+(\d+\.\d+)\s+(.*)$", line):
                current = (m.group(1), m.group(2).strip())
        elif current and line.strip():
            body.append(line.strip())
    return sections


class PolicyChoice(BaseModel):
    covered: bool                                      # False: the policy does not address the question
    section_ids: list[str] = Field(max_length=2)


SYSTEM = """You match an Indian online shopper's question (often Hinglish) to the store policy below.
Return the ID of the one sub-section that answers it; add a second only if the answer truly needs both.
Set covered=false and section_ids=[] if no sub-section addresses the question (for example loyalty points, EMI,
gift wrapping, installation): never pick a loosely related section.

Store policy sub-sections:
{sections}"""


class PolicyAnswerer:
    def __init__(self, llm: LLM, sections: list[PolicySection]):
        self.llm, self.sections = llm, {s.id: s for s in sections}
        listing = "\n".join(f"{s.id} {s.title}: {s.text}" for s in sections)
        self.system = SYSTEM.format(sections=listing)
        schema = PolicyChoice.model_json_schema()
        schema["properties"]["section_ids"]["items"]["enum"] = list(self.sections)
        self.json_schema = schema

    def choose(self, question: str, history: list[str] | None = None) -> tuple[list[PolicySection], LLMUsage]:
        earlier = ("Earlier messages: " + " | ".join(history) + "\n") if history else ""
        choice, usage = self.llm.chat_json(self.system, f"{earlier}Shopper question: {question}", PolicyChoice,
                                           json_schema=self.json_schema)
        picked = [self.sections[i] for i in dict.fromkeys(choice.section_ids) if i in self.sections]
        return (picked if choice.covered else []), usage
