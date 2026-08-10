"""Provider-neutral structured reasoning over a pluggable chat transport.

Every reasoning stage decides the same three things regardless of which vendor answers
it: what the model is told, which handles it may reference, and what shape the reply
must take. Those decisions live here, once. A `ChatTransport` owns only the part that
genuinely differs between vendors - request options, timeouts, retries, and translating
a failure into `ProviderError`.

This split is what `separate-model-context-from-provider-transport` asks for: the
semantic context and its response grammar are assembled above the transport boundary,
and an adapter merely encodes an already-decided request.

Four modules, and `reasoning_stages` is the one to read first — it is the stages
themselves, and the other three are what they are built out of: `chat_transports` (how a
vendor is spoken to), `investigation_loop` (the turns a stage may spend looking things
up), `reply_schemas` (what a reply may look like and what is made of it).

This file is the package's import surface and stays one: `from
archcompass.adapters.models.structured import ...` names the same things it always did,
whichever module they moved into.
"""

from archcompass.adapters.models.structured.chat_transports import (
    AssistantToolTurn,
    ChatMessage,
    ChatTransport,
    InvestigationMessage,
    ProsePreview,
    StreamingChatTransport,
    ThinkLevel,
    ToolCall,
    ToolCallingChatTransport,
    ToolExchange,
    ToolResultTurn,
    accumulate_reply,
    prose_prefix,
)
from archcompass.adapters.models.structured.investigation_loop import (
    MAX_INVESTIGATION_CHARACTERS,
    MAX_INVESTIGATION_TURNS,
    investigate,
)
from archcompass.adapters.models.structured.reasoning_stages import (
    StructuredReasoningProvider,
)
from archcompass.adapters.models.structured.reply_schemas import (
    ProposedCandidateVerdict,
    ProposedElicitation,
    ProposedOpenQuestion,
    ProposedOverviewStatement,
    ProposedPolicyBearing,
    ProposedQuestionDiscussion,
    ProposedReviewAnswer,
    ProposedReviewOverview,
    ProposedVerdictHinge,
    grounded_questions,
    grounded_schema,
    grounded_statements,
    opening_capital,
    prose_defects,
    review_answer_schema,
    tidied_options,
    verdict_hinge,
    verdict_schema,
)

__all__ = [
    "MAX_INVESTIGATION_CHARACTERS",
    "MAX_INVESTIGATION_TURNS",
    "AssistantToolTurn",
    "ChatMessage",
    "ChatTransport",
    "InvestigationMessage",
    "ProposedCandidateVerdict",
    "ProposedElicitation",
    "ProposedOpenQuestion",
    "ProposedOverviewStatement",
    "ProposedPolicyBearing",
    "ProposedQuestionDiscussion",
    "ProposedReviewAnswer",
    "ProposedReviewOverview",
    "ProposedVerdictHinge",
    "ProsePreview",
    "StreamingChatTransport",
    "StructuredReasoningProvider",
    "ThinkLevel",
    "ToolCall",
    "ToolCallingChatTransport",
    "ToolExchange",
    "ToolResultTurn",
    "accumulate_reply",
    "grounded_questions",
    "grounded_schema",
    "grounded_statements",
    "investigate",
    "opening_capital",
    "prose_defects",
    "prose_prefix",
    "review_answer_schema",
    "tidied_options",
    "verdict_hinge",
    "verdict_schema",
]
