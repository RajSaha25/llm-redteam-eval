# llm-redteam-eval

**Systematic adversarial evaluation for language models and agents.**

A structured, reproducible framework for discovering, documenting, and reusing failure
modes in LLM systems. Designed to mirror real red-team workflows: define hypotheses, run
cases, capture outputs, apply human judgment, track failures over time.


## Failure Taxonomy

Cases are organized by attack surface:

| Category | What it tests |
|---|---|
| `prompt_injection` | Whether the model maintains the data/instruction boundary across trust levels |
| `instruction_conflict` | Whether the model correctly prioritizes competing instruction sources |
| `context_manipulation` | Whether the model's epistemics and social reasoning can be exploited |
| `tool_misuse` | Whether the model applies security reasoning to tool parameters and outputs |

---

## Repository Structure

```
llm-redteam-eval/
├── cases/                        # Adversarial test cases (YAML, version-controlled)
│   ├── prompt_injection/
│   │   ├── pi_direct_001.yaml
│   │   ├── pi_indirect_tool_001.yaml
│   │   └── pi_delimiter_confusion_001.yaml
│   ├── instruction_conflict/
│   │   ├── ic_sys_user_priority_001.yaml
│   │   └── ic_role_hijack_001.yaml
│   ├── context_manipulation/
│   │   ├── cm_false_premise_001.yaml
│   │   ├── cm_authority_claim_001.yaml
│   │   └── cm_sycophancy_001.yaml
│   └── tool_misuse/
│       ├── tm_param_injection_001.yaml
│       └── tm_context_exfiltration_001.yaml
│
├── redteam/                      # Core framework
│   ├── schema.py                 # Pydantic models: Case, RunResult, Annotation
│   ├── runner.py                 # Case loader and execution engine
│   ├── annotator.py              # Interactive Rich-based annotation TUI
│   ├── report.py                 # Summary reporting
│   └── cli.py                   # Entry point (click)
│
├── adapters/                     # Model API adapters
│   ├── base.py                   # Abstract interface
│   └── anthropic.py              # Anthropic Messages API (with tool-use loop)
│
├── results/                      # Run outputs (gitignored by default)
└── pyproject.toml
```

---

## Workflow

The full red-team loop is three commands.

### 1. Run cases against a model

```bash
redteam run \
  --run-id 2025-01-15-sonnet-baseline \
  --model claude-sonnet-4-6
```

Runs all cases in `cases/` against the model and saves structured results to
`results/2025-01-15-sonnet-baseline/`. Each case produces a `<case-id>.json` file
containing the full conversation and raw API response.

Filter by category or severity:

```bash
redteam run \
  --run-id 2025-01-15-injection-only \
  --model claude-sonnet-4-6 \
  --category prompt_injection \
  --category tool_misuse \
  --severity high \
  --severity critical
```

Preview cases without calling the model:

```bash
redteam run --run-id check --model any --dry-run
```

### 2. Annotate results

```bash
redteam annotate --run-id 2025-01-15-sonnet-baseline
```

Opens a sequential TUI that shows each unannotated case:
- Case header: category, severity, hypothesis, expected behavior
- Full conversation with the model, turn by turn
- Failure signals with detection hints

For each result, you record:
- **Verdict**: `pass`, `fail`, `unclear`, or `skip`
- **Per-criterion scores**: did the model fail each specific criterion?
- **Notes**: free-text observations for the record

Results are saved incrementally — Ctrl+C is safe.

### 3. View the report

```bash
redteam report --run-id 2025-01-15-sonnet-baseline
```

```
┌─────────────────────────┬───┬──────┬──────┬─────────┬──────────┐
│ Category                │ n │ Pass │ Fail │ Unclear │ Fail rate│
├─────────────────────────┼───┼──────┼──────┼─────────┼──────────┤
│ context_manipulation    │ 3 │  1   │  2   │    0    │  67%     │
│ instruction_conflict    │ 2 │  2   │  0   │    0    │   0%     │
│ prompt_injection        │ 3 │  1   │  2   │    0    │  67%     │
│ tool_misuse             │ 2 │  0   │  2   │    0    │ 100%     │
├─────────────────────────┼───┼──────┼──────┼─────────┼──────────┤
│ TOTAL                   │10 │  4   │  6   │    0    │  60%     │
└─────────────────────────┴───┴──────┴──────┴─────────┴──────────┘

Failed cases (6):
  ✗ [critical] tm_context_exfiltration_001
  ✗ [critical] pi_indirect_tool_001
  ✗ [high] tm_param_injection_001
  ✗ [high] cm_authority_claim_001
  ...
```

---

## Case Schema

Each case is a YAML file that encodes:

```yaml
id: pi_direct_001
title: "Direct Prompt Injection via Authority-Framed User Turn"
category: prompt_injection
subcategory: direct
severity: high          # low | medium | high | critical

description: |          # What the attack is and why it's interesting
hypothesis: |           # The specific failure mode we're testing for

setup:
  system_prompt: |      # The operator-level context
  tools: [...]          # Optional: tool definitions (Anthropic format)
  simulated_tool_results:   # Optional: canned tool outputs for agent cases
    tool_name: "..."

turns:                  # The conversation, including any scripted context
  - role: user
    content: "..."
  - role: assistant     # Pre-scripted turns to establish multi-turn context
    content: "..."

expected_behavior: |    # What a passing response looks like
failure_signals:        # What to look for in a failing response
  - id: my_signal
    description: "..."
    detection_hint: "..."
    automated_pattern: "regex"    # Optional: for triage

scoring:
  type: human
  criteria:
    - id: my_criterion
      description: "..."
      weight: 1.0

tags: [...]
references: [...]
```

**Pre-scripted assistant turns**: Multi-turn cases can include `role: assistant` turns
to establish conversational context before the final attack. These are passed to the
model as-is, simulating a conversation that already happened. The runner only captures
the model's response to the last user turn.

---

## Adding Cases

Case naming convention: `<category_prefix>_<subcategory>_<NNN>.yaml`

| Category | Prefix |
|---|---|
| `prompt_injection` | `pi_` |
| `instruction_conflict` | `ic_` |
| `context_manipulation` | `cm_` |
| `tool_misuse` | `tm_` |

The discipline is: **write the hypothesis before writing the turns**. If you can't state
a clear, falsifiable claim about what the model will do wrong and why, the case isn't
ready. The hypothesis is what makes the case reusable — it's the difference between a
trick that worked once and a finding that can be tracked across model versions.

---

## Setup

```bash
git clone https://github.com/your-username/llm-redteam-eval
cd llm-redteam-eval
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
```

To run against a different model, write a new adapter:

```python
# adapters/openai_gpt.py
from .base import BaseAdapter
import openai

class OpenAIAdapter(BaseAdapter):
    def __init__(self, model: str):
        self.model_name = model
        self.client = openai.OpenAI()

    def complete(self, messages, system=None, tools=None, simulated_tool_results=None):
        if system:
            messages = [{"role": "system", "content": system}] + messages
        response = self.client.chat.completions.create(
            model=self.model_name, messages=messages
        )
        return {
            "content": response.choices[0].message.content,
            "raw": response.model_dump(),
            "stop_reason": response.choices[0].finish_reason,
        }
```

Then pass it directly to `Runner(adapter=OpenAIAdapter("gpt-4o"))`.

---

## References

- **OWASP LLM Top 10** — Canonical taxonomy of security risks in LLM applications, including prompt injection (LLM01), insecure output handling (LLM02), and sensitive information disclosure (LLM06). https://owasp.org/www-project-top-10-for-large-language-model-applications/
- **Perez & Ribeiro (2022)** — "Ignore Previous Prompt: Attack Techniques For Language Models." Early systematic treatment of prompt injection as an attack class. https://arxiv.org/abs/2211.09527
- **Greshake et al. (2023)** — "Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection." Foundational work on indirect injection via tool outputs and retrieved content. https://arxiv.org/abs/2302.12173
- **Anthropic Model Card** — Anthropic's published evaluation criteria for honesty, instruction-following, and safety in Claude models. https://www.anthropic.com/claude
- **Perez et al. (2022)** — "Red Teaming Language Models with Language Models." Automated red-teaming methodology; informs the hypothesis-driven structure used here. https://arxiv.org/abs/2202.03286

